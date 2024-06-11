import re
import json
import geojson
import pyproj
from shapely import wkt
from shapely.geometry import shape
from shapely.ops import transform
from uuid import uuid4
from rdflib import URIRef
import graphdb as gd
import graphrdf as gr

def from_geojson_to_wkt(geojson_obj:dict):
    a = json.dumps(geojson_obj)
    geo = geojson.loads(a)
    geom = shape(geo)

    return geom.wkt

def merge_geojson_features_from_one_property(feature_collection, property_name:str):
    """
    Merge all features of a geojson object which have the same property (name for instance)
    """

    new_geojson_features = []
    features_to_merge = {}
    
    features_key = "features"
    crs_key = "crs"

    for feat in feature_collection.get(features_key):
        # Get property value for the feature
        property_value = feat.get("properties").get(property_name)

        # If the value is blank or does not exist, generate an uuid
        if property_value in [None, ""]:
            empty_value = True
            property_value = uuid4().hex
            feature_template = {"type":"Feature", "properties":{}}
        else:
            empty_value = False
            feature_template = {"type":"Feature", "properties":{property_name:property_value}}

        features_to_merge_key = features_to_merge.get(property_value)

        if features_to_merge_key is None:
            features_to_merge[property_value] = [feature_template, [feat]]
        else:
            features_to_merge[property_value][1].append(feat)

    for elem in features_to_merge.values():
        template, feature = elem

        geom_collection_list = []
        for portion in feature:
            geom_collection_list.append(portion.get("geometry"))
    
        geom_collection = {"type": "GeometryCollection", "geometries": geom_collection_list}
        template["geometry"] = geom_collection
        new_geojson_features.append(template)

    new_geojson = {"type":"FeatureCollection", features_key:new_geojson_features}

    crs_value = feature_collection.get(crs_key)
    if crs_value is not None :
        new_geojson[crs_key] = crs_value

    return new_geojson

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

def get_wkt_geom_from_geosparql_wktliteral(wktliteral:str):
    """
    Extraire le WKT et le l'URI SRID de la géométrie si elle est indiquée
    """

    wkt_srid_pattern = "<(.{0,})>"
    wkt_value_pattern = "<.{0,}> {1,}"
    wkt_geom_srid_match = re.match(wkt_srid_pattern, wktliteral)
    
    epsg_4326_uri = URIRef("http://www.opengis.net/def/crs/EPSG/0/4326")
    crs84_uri = URIRef("http://www.opengis.net/def/crs/OGC/1.3/CRS84")

    if wkt_geom_srid_match is not None:
        wkt_geom_srid = URIRef(wkt_geom_srid_match.group(1))
    else:
        wkt_geom_srid = epsg_4326_uri

    if wkt_geom_srid == crs84_uri:
        wkt_geom_srid = epsg_4326_uri
    wkt_geom_value = re.sub(wkt_value_pattern, "", wktliteral)

    return wkt_geom_value, wkt_geom_srid

def transform_geometry_crs(geom, crs_from, crs_to):
    """
    Obtenir une géométrie définie dans le système de coordonnées `from_crs` vers le système `to_crs`.
    """

    project = pyproj.Transformer.from_crs(crs_from, crs_to, always_xy=True).transform
    return transform(project, geom)

def get_pyproj_crs_from_opengis_epsg_uri(opengis_epsg_uri:URIRef):
    """
    Extraction du code EPSG à partir de `opengis_epsg_uri` pour renvoyer un objet pyproj.CRS
    """
    pattern = "http://www.opengis.net/def/crs/EPSG/0/([0-9]{1,})"
    try :
        epsg_code = re.match(pattern, opengis_epsg_uri.strip()).group(1)
        return pyproj.CRS(f'EPSG:{epsg_code}')
    except :
        return None

def are_similar_geometries(geom_1, geom_2, coef_min:float) -> bool:
    """
    La fonction détermine si deux géométries sont similaires
    `coef_min` est dans [0,1] et définit la valeur minimale pour considérer que `geom_1` et `geom_2` soient similaires
    """
    # geom_intersection = geom_1.intersection(geom_2)
    # geom_union = geom_1.union(geom_2)
    # coef = geom_intersection.area/geom_union.area

    # if coef > 0.7:
    #     return True
    # else:
    #     return False

    geom_intersection = geom_1.envelope.intersection(geom_2.envelope)
    geom_union = geom_1.envelope.union(geom_2.envelope)
    coef = geom_intersection.area/geom_union.area

    if coef >= coef_min:
        return True
    else:
        return False

def get_processed_geometry(geom_wkt:str, geom_srid_uri:URIRef, crs_uri:URIRef, buffer_radius:float):
    """
    Obtention d'une géométrie pour pouvoir la comparer aux autres :
    * ses coordonnées seront exprimées dans le référentiel lié à `crs_uri`
    * si la géométrie est une ligne ou un point (area=0.0), alors on récupère une zone tampon dont le buffer est donné par `buffer_radius`
    """

    geom = wkt.loads(geom_wkt)
    crs_from = get_pyproj_crs_from_opengis_epsg_uri(geom_srid_uri)
    crs_to = get_pyproj_crs_from_opengis_epsg_uri(crs_uri)

    # Conversion de la géométrie vers le système de coordonnées cible
    if crs_from != crs_to:
        geom = transform_geometry_crs(geom, crs_from, crs_to)
    
    # Ajout d'un buffer `meter_buffer` mètres si c'est pas un polygone
    if geom.area == 0.0:
        geom = geom.buffer(buffer_radius)

    return geom

def get_geometry_versions(graphdb_url:str, repository_name:str, query_prefixes:str, crs_uri:URIRef, buffer_radius:float):
    """
    Récupération des versions de géométrie dans le répertoire, on les regroupe par attribut et on exprime l'ensemble des géométries dans le système de coordonnées défini par `crs_uri`.
    Si les géométries sont des points ou des lignes, on travaille avec une zone tampon autour de ces dernières dont la distance est définie par `buffer_radius`
    """

    query = query_prefixes + """
        SELECT ?attr ?av ?geom WHERE {
            ?attr a addr:Attribute ; addr:isAttributeType atype:Geometry ; addr:hasAttributeVersion ?av.
            ?av addr:versionValue ?geom.
        }
        """
    
    a = gd.select_query_to_json(query, graphdb_url, repository_name)
    geom_versions = {}

    for elem in a.get("results").get("bindings"):
        # Récupération des URIs (attibut et version d'attribut) et de la géométrie
        rel_attr = gr.convert_result_elem_to_rdflib_elem(elem.get('attr'))
        rel_av = gr.convert_result_elem_to_rdflib_elem(elem.get('av'))
        rel_geom = gr.convert_result_elem_to_rdflib_elem(elem.get('geom'))

        if rel_attr not in geom_versions.keys():
            geom_versions[rel_attr] = {}

        geom_wkt, geom_srid_uri = get_wkt_geom_from_geosparql_wktliteral(rel_geom.strip())
        geom = get_processed_geometry(geom_wkt, geom_srid_uri, crs_uri, buffer_radius)
        geom_versions[rel_attr][rel_av] = geom

    return geom_versions

def compare_geometry_versions(graphdb_url:str, repository_name:str, namespace_prefixes:dict, comp_named_graph_name:str, crs_uri:URIRef, buffer_radius:float, similarity_coef=0.8):
    """
    Pour chaque attribut de géométrie lié à un landmark, on compare ses versions et on indique si leur valeur sont similaires ou pas.
    Soient v1 et v2 deux versions.
    Si elles ont des valeurs similaires, alors <v1 addr:sameVersionValueAs v2>, sinon <v1 addr:differentVersionValueFrom v2>
    """
    
    query_prefixes = gd.get_query_prefixes_from_namespaces(namespace_prefixes) # Préfixes en en-tête des requêtes SPARQL
    geom_versions = get_geometry_versions(graphdb_url, repository_name, query_prefixes, crs_uri, buffer_radius)
    version_comparisons = []
    for attr_vers_uris in geom_versions.values():
        for attr_vers_uri_1, geom_1 in attr_vers_uris.items():
            for attr_vers_uri_2, geom_2 in attr_vers_uris.items():
                if attr_vers_uri_1 != attr_vers_uri_2:
                    sim_geoms = are_similar_geometries(geom_1, geom_2, similarity_coef)
                    version_comparisons.append((attr_vers_uri_1, attr_vers_uri_2, sim_geoms))

    comp_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, comp_named_graph_name))
    query = get_insert_data_query_for_version_comparisons(version_comparisons, query_prefixes, comp_named_graph_uri)

    gd.update_query(query, graphdb_url, repository_name)