import geomprocessing as gp
import strprocessing as sp
import graphdb as gd
import graphrdf as gr
from rdflib import URIRef

def get_insert_data_query_for_version_comparisons(version_comparisons:list[tuple], query_prefixes:str, named_graph_uri:URIRef=None) -> str:
    """
    Construction d'une requête SPARQL permettant d'insérer des triplets indiquant si les versions d'attributs ont des valeurs similaires ou pas
    * `version_comparisons` : liste de 3-tuples dont les deux premières valeurs sont des URI des versions et la dernière est un booléen indiquant True si les URI ont des valeurs similaires, False sinon
    * `named_graph_uri` est l'URI du graphe nommé dans lequel on veut insérer les triplets, None par défaut (dans le graphe par défaut)
    """

    query_lines = ""
    for comp in version_comparisons:
        if comp[2]:
            pred = "addr:sameVersionValueAs"
        else:
            pred = "addr:differentVersionValueFrom"

        query_lines += f"{comp[0].n3()} {pred} {comp[1].n3()} .\n"

    if named_graph_uri is None:
        opened_named_graph = ""
        closed_named_graph = ""
    else:
        opened_named_graph = f"GRAPH {named_graph_uri.n3()} {{"
        closed_named_graph = f"}}"
        
    query = query_prefixes + f"""
        INSERT DATA {{
        {opened_named_graph}
        {query_lines}
        {closed_named_graph}
        }} 
        """

    return query

def compare_geometry_versions(graphdb_url:str, repository_name:str, namespace_prefixes:dict, facts_named_graph_name:str, comp_named_graph_name:str, crs_uri:URIRef, buffer_radius:float, similarity_coef=0.8):
    """
    Pour chaque attribut de géométrie lié à un landmark, on compare ses versions et on indique si leur valeur sont similaires ou pas.
    Soient v1 et v2 deux versions.
    Si elles ont des valeurs similaires, alors <v1 addr:sameVersionValueAs v2>, sinon <v1 addr:differentVersionValueFrom v2>
    """
    
    query_prefixes = gd.get_query_prefixes_from_namespaces(namespace_prefixes) # Préfixes en en-tête des requêtes SPARQL
    geom_versions, geom_types = get_geometry_versions(graphdb_url, repository_name, query_prefixes, facts_named_graph_uri, crs_uri, buffer_radius)
    version_comparisons = []
    for attr_uri, attr_vers_uris in geom_versions.items():
        geom_type = geom_types.get(attr_uri)
        for attr_vers_uri_1, geom_1 in attr_vers_uris.items():
            for attr_vers_uri_2, geom_2 in attr_vers_uris.items():
                if attr_vers_uri_1 != attr_vers_uri_2:
                    sim_geoms = gp.are_similar_geometries(geom_1, geom_2, geom_type, similarity_coef, max_dist=buffer_radius)
                    version_comparisons.append((attr_vers_uri_1, attr_vers_uri_2, sim_geoms))

    comp_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, comp_named_graph_name))
    facts_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, facts_named_graph_name))
    query = get_insert_data_query_for_version_comparisons(version_comparisons, query_prefixes, comp_named_graph_uri)

    gd.update_query(query, graphdb_url, repository_name)

def compare_name_versions(graphdb_url, repository_name, namespace_prefixes, facts_named_graph_name:str, comp_named_graph_name, similarity_coef):
    query_prefixes = gd.get_query_prefixes_from_namespaces(namespace_prefixes) # Préfixes en en-tête des requêtes SPARQL
    name_versions = get_name_versions(graphdb_url, repository_name, query_prefixes, facts_named_graph_name)

    version_comparisons = []
    for attr_uri, attr_vers_uris in name_versions.items():
        for attr_vers_uri_1, name_1 in attr_vers_uris.items():
            for attr_vers_uri_2, name_2 in attr_vers_uris.items():
                if attr_vers_uri_1 != attr_vers_uri_2:
                    sim_names = sp.are_similar_names(name_1, name_2, similarity_coef)
                    version_comparisons.append((attr_vers_uri_1, attr_vers_uri_2, sim_names))

    comp_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, comp_named_graph_name))
    query = get_insert_data_query_for_version_comparisons(version_comparisons, query_prefixes, comp_named_graph_uri)

    gd.update_query(query, graphdb_url, repository_name)

def get_geometry_versions(graphdb_url:str, repository_name:str, query_prefixes:str, named_graph_uri:URIRef, crs_uri:URIRef, buffer_radius:float):
    """
    Récupération des versions de géométrie dans le répertoire, on les regroupe par attribut et on exprime l'ensemble des géométries dans le système de coordonnées défini par `crs_uri`.
    Si les géométries sont des points ou des lignes, on travaille avec une zone tampon autour de ces dernières dont la distance est définie par `buffer_radius`
    """

    query = query_prefixes + f"""
        SELECT ?attr ?av ?geom ?geomType WHERE {{
            BIND({named_graph_uri.n3()} AS ?g)
            ?attr a addr:Attribute ; addr:isAttributeType atype:Geometry ; addr:hasAttributeVersion ?av ; addr:isAttributeOf [addr:isLandmarkType ?ltype] . 
            GRAPH ?g {{ ?av addr:versionValue ?geom . }}
            BIND(IF(?ltype IN (ltype:HouseNumber, ltype:StreetNumber, ltype:DistrictNumber), "point", "polygon") AS ?geomType)
        }}
        """
    
    results = gd.select_query_to_json(query, graphdb_url, repository_name)
    geom_versions, geom_types = {}, {}

    for elem in results.get("results").get("bindings"):
        # Récupération des URIs (attibut et version d'attribut) et de la géométrie
        rel_attr = gr.convert_result_elem_to_rdflib_elem(elem.get('attr'))
        rel_av = gr.convert_result_elem_to_rdflib_elem(elem.get('av'))
        rel_geom = gr.convert_result_elem_to_rdflib_elem(elem.get('geom'))
        rel_geom_type = gr.convert_result_elem_to_rdflib_elem(elem.get('geomType'))

        if rel_attr not in geom_versions.keys():
            geom_versions[rel_attr] =  {}
            geom_types[rel_attr] = rel_geom_type.strip()

        geom_wkt, geom_srid_uri = gp.get_wkt_geom_from_geosparql_wktliteral(rel_geom.strip())
        geom = gp.get_processed_geometry(geom_wkt, geom_srid_uri, rel_geom_type, crs_uri, buffer_radius)
        geom_versions[rel_attr][rel_av] = geom

    return geom_versions, geom_types

def get_name_versions(graphdb_url:str, repository_name:str, query_prefixes:str, named_graph_uri:URIRef):
    query = query_prefixes + f"""
        SELECT ?attr ?av ?name ?nameType WHERE {{
            BIND({named_graph_uri.n3()} AS ?g)
            GRAPH ?g {{ ?av skos:hiddenLabel ?name . }}
            ?attr a addr:Attribute ; addr:isAttributeType atype:Name ; addr:hasAttributeVersion ?av ; addr:isAttributeOf [addr:isLandmarkType ?ltype] . 
            BIND(IF(?ltype IN (ltype:HouseNumber, ltype:StreetNumber, ltype:DistrictNumber), "housenumber", 
                IF(?ltype = ltype:Thoroughfare, "thoroughfare", 
                    IF(?ltype IN (ltype:City, ltype:District, ltype:PostalCodeArea), "area", ""))) AS ?nameType)
        }}
        """
    
    results = gd.select_query_to_json(query, graphdb_url, repository_name)
    name_versions = {}

    for elem in results.get("results").get("bindings"):
        # Récupération des URIs (attibut et version d'attribut) et de la géométrie
        rel_attr = gr.convert_result_elem_to_rdflib_elem(elem.get('attr'))
        rel_av = gr.convert_result_elem_to_rdflib_elem(elem.get('av'))
        rel_name = gr.convert_result_elem_to_rdflib_elem(elem.get('name'))
        rel_name_type = gr.convert_result_elem_to_rdflib_elem(elem.get('nameType'))
        
        # normalized_name, simplified_name = normalize_and_simplified_name_version(rel_name.strip(), rel_name_type.strip())

        if rel_attr not in name_versions.keys():
            name_versions[rel_attr] =  {}

        name_versions[rel_attr][rel_av] = [rel_name.strip()]

    return name_versions