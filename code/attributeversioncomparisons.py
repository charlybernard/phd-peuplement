from namespaces import NameSpaces
import geomprocessing as gp
import strprocessing as sp
import graphdb as gd
import graphrdf as gr
from rdflib import URIRef

np = NameSpaces()



def get_insert_data_query_for_version_comparisons(version_comparisons:list[tuple], named_graph_uri:URIRef=None) -> str:
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
        
    query = np.query_prefixes + f"""
        INSERT DATA {{
        {opened_named_graph}
        {query_lines}
        {closed_named_graph}
        }} 
        """

    return query

def compare_attribute_versions(graphdb_url:str, repository_name:str, facts_named_graph_name:str, comp_named_graph_name:str, comparison_settings:dict={}):
    results = get_attribute_versions_to_compare(graphdb_url, repository_name)
    version_comparisons = []
    for elem in results.get("results").get("bindings"):
        # Récupération des URIs (attibut et version d'attribut)
        attr_type = gr.convert_result_elem_to_rdflib_elem(elem.get('attrType'))
        lm_type = gr.convert_result_elem_to_rdflib_elem(elem.get('ltype'))
        attr_vers_1 = gr.convert_result_elem_to_rdflib_elem(elem.get('attrVers1'))
        attr_vers_2 = gr.convert_result_elem_to_rdflib_elem(elem.get('attrVers2'))
        vers_val_1 = gr.convert_result_elem_to_rdflib_elem(elem.get('versVal1'))
        vers_val_2 = gr.convert_result_elem_to_rdflib_elem(elem.get('versVal2'))

        if attr_type == np.ATYPE["Name"]:
            is_same_value = are_similar_name_versions(lm_type, vers_val_1, vers_val_2)
  
        elif attr_type == np.ATYPE["Geometry"]:
            similarity_coef = comparison_settings.get("geom_similarity_coef")
            buffer_radius = comparison_settings.get("geom_buffer_radius")
            crs_uri = comparison_settings.get("geom_crs_uri")
            is_same_value = are_similar_geom_versions(lm_type, vers_val_1, vers_val_2, similarity_coef, buffer_radius, crs_uri)
        else:
            is_same_value = False

        version_comparisons.append((attr_vers_1, attr_vers_2, is_same_value))
        comp_named_graph_uri = gd.get_named_graph_uri_from_name(graphdb_url, repository_name, comp_named_graph_name)
        query = get_insert_data_query_for_version_comparisons(version_comparisons, comp_named_graph_uri)
        gd.update_query(query, graphdb_url, repository_name)
        
def get_geom_type_according_landmark_type(rel_lm_type:URIRef):
    if rel_lm_type in [np.LTYPE["HouseNumber"], np.LTYPE["StreetNumber"], np.LTYPE["DistrictNumber"]]:
        return "point"
    elif rel_lm_type in [np.LTYPE["Thoroughfare"], np.LTYPE["District"], np.LTYPE["City"]]:
        return "polygon"
    else:
        return "polygon"

def get_name_type_according_landmark_type(rel_lm_type:URIRef):
    if rel_lm_type in [np.LTYPE["HouseNumber"], np.LTYPE["StreetNumber"], np.LTYPE["DistrictNumber"]]:
        return "housenumber"
    elif rel_lm_type in [np.LTYPE["Thoroughfare"]]:
        return "thoroughfare"
    elif rel_lm_type in [np.LTYPE["District"], np.LTYPE["City"]]:
        return "area"
    else:
        return ""

def are_similar_geom_versions(lm_type, vers_val_1, vers_val_2, similarity_coef, buffer_radius, crs_uri):
    geom_type = get_geom_type_according_landmark_type(lm_type)
    geom_wkt_1, geom_srid_uri_1 = gp.get_wkt_geom_from_geosparql_wktliteral(vers_val_1.strip())
    geom_1 = gp.get_processed_geometry(geom_wkt_1, geom_srid_uri_1, geom_type, crs_uri, buffer_radius)
    geom_wkt_2, geom_srid_uri_2 = gp.get_wkt_geom_from_geosparql_wktliteral(vers_val_2.strip())
    geom_2 = gp.get_processed_geometry(geom_wkt_2, geom_srid_uri_2, geom_type, crs_uri, buffer_radius)

    return gp.are_similar_geometries(geom_1, geom_2, geom_type, similarity_coef, max_dist=buffer_radius)

def are_similar_name_versions(lm_type, vers_val_1, vers_val_2):
    name_type = get_name_type_according_landmark_type(lm_type)
    normalized_name_1, simplified_name_1 = sp.normalize_and_simplify_name_version(vers_val_1.strip(), name_type, name_lang=vers_val_1.language)
    normalized_name_2, simplified_name_2 = sp.normalize_and_simplify_name_version(vers_val_2.strip(), name_type, name_lang=vers_val_2.language)

    if normalized_name_1 == normalized_name_2:
        return True
    else:
        return False

def get_attribute_versions_to_compare(graphdb_url:str, repository_name:str):
    query = np.query_prefixes  + f"""
        SELECT DISTINCT ?ltype ?attrType ?attrVers1 ?attrVers2 ?versVal1 ?versVal2 WHERE {{
            ?rootLm addr:isRootLandmarkOf ?lm1, ?lm2.
            ?lm1 addr:hasAttribute [addr:isAttributeType ?attrType ; addr:hasAttributeVersion ?attrVers1] ; addr:isLandmarkType ?ltype .
            ?lm2 addr:hasAttribute [addr:isAttributeType ?attrType ; addr:hasAttributeVersion ?attrVers2] .
            ?attrVers1 addr:versionValue ?versVal1 .
            ?attrVers2 addr:versionValue ?versVal2 .
            FILTER(!sameTerm(?lm1, ?lm2))
            MINUS {{
                ?attrVers1 ?p ?attrVers2 .
                FILTER(?p IN (addr:sameVersionValueAs, addr:differentVersionValueFrom))
            }}
        }}
    """

    results = gd.select_query_to_json(query, graphdb_url, repository_name)

    return results

def compare_geometry_versions(graphdb_url:str, repository_name:str, facts_named_graph_name:str, comp_named_graph_name:str, crs_uri:URIRef, buffer_radius:float, similarity_coef=0.8):
    """
    Pour chaque attribut de géométrie lié à un landmark, on compare ses versions et on indique si leur valeur sont similaires ou pas.
    Soient v1 et v2 deux versions.
    Si elles ont des valeurs similaires, alors <v1 addr:sameVersionValueAs v2>, sinon <v1 addr:differentVersionValueFrom v2>
    """

    comp_named_graph_uri = gd.get_named_graph_uri_from_name(graphdb_url, repository_name, comp_named_graph_name)
    facts_named_graph_uri = gd.get_named_graph_uri_from_name(graphdb_url, repository_name, facts_named_graph_name)
    
    geom_versions, geom_types = get_geometry_versions(graphdb_url, repository_name, facts_named_graph_uri, crs_uri, buffer_radius)
    version_comparisons = []
    
    for attr_uri, attr_vers_uris in geom_versions.items():
        geom_type = geom_types.get(attr_uri)
        for attr_vers_uri_1, geom_1 in attr_vers_uris.items():
            for attr_vers_uri_2, geom_2 in attr_vers_uris.items():
                if attr_vers_uri_1 != attr_vers_uri_2:
                    sim_geoms = gp.are_similar_geometries(geom_1, geom_2, geom_type, similarity_coef, max_dist=buffer_radius)
                    version_comparisons.append((attr_vers_uri_1, attr_vers_uri_2, sim_geoms))

    query = get_insert_data_query_for_version_comparisons(version_comparisons, comp_named_graph_uri)
    gd.update_query(query, graphdb_url, repository_name)

def compare_name_versions(graphdb_url, repository_name, facts_named_graph_name:str, comp_named_graph_name, similarity_coef):
    comp_named_graph_uri = gd.get_named_graph_uri_from_name(graphdb_url, repository_name, comp_named_graph_name)
    facts_named_graph_uri = gd.get_named_graph_uri_from_name(graphdb_url, repository_name, facts_named_graph_name)
    
    name_versions = get_name_versions(graphdb_url, repository_name, facts_named_graph_uri)

    version_comparisons = []
    for attr_vers_uris in name_versions.values():
        for attr_vers_uri_1, name_1 in attr_vers_uris.items():
            for attr_vers_uri_2, name_2 in attr_vers_uris.items():
                if attr_vers_uri_1 != attr_vers_uri_2:
                    sim_names = sp.are_similar_names(name_1, name_2, similarity_coef)
                    version_comparisons.append((attr_vers_uri_1, attr_vers_uri_2, sim_names))

    query = get_insert_data_query_for_version_comparisons(version_comparisons, comp_named_graph_uri)

    gd.update_query(query, graphdb_url, repository_name)

def get_geometry_versions(graphdb_url:str, repository_name:str, named_graph_uri:URIRef, crs_uri:URIRef, buffer_radius:float):
    """
    Récupération des versions de géométrie dans le répertoire, on les regroupe par attribut et on exprime l'ensemble des géométries dans le système de coordonnées défini par `crs_uri`.
    Si les géométries sont des points ou des lignes, on travaille avec une zone tampon autour de ces dernières dont la distance est définie par `buffer_radius`
    """

    query = np.query_prefixes + f"""
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

def get_name_versions(graphdb_url:str, repository_name:str, named_graph_uri:URIRef):
    query = np.query_prefixes + f"""
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
        
        # normalized_name, simplified_name = normalize_and_simplify_name_version(rel_name.strip(), rel_name_type.strip())

        if rel_attr not in name_versions.keys():
            name_versions[rel_attr] =  {}

        name_versions[rel_attr][rel_av] = [rel_name.strip()]

    return name_versions