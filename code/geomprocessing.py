import re
import json
import geojson
from shapely.geometry import shape
from uuid import uuid4

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

def get_wkt_geom_from_geosparql_wktliteral(wktliteral:str):
    """
    Extraire le srid de la géométrie WKT et la géométrie WKT venant d'un wktLiteral geosqparql
    """
    
    wkt_srid_pattern = "<.{0,}>"
    wkt_value_pattern = "<.{0,}> {1,}"
    wkt_geom_srid_match = re.match(wkt_srid_pattern, wktliteral)

    if wkt_geom_srid_match is not None:
        wkt_geom_srid = wkt_geom_srid_match.group(0)
    else:
        wkt_geom_srid = "<http://www.opengis.net/def/crs/OGC/1.3/CRS84>"

    wkt_geom_value = re.sub(wkt_value_pattern, "", wktliteral)

    return wkt_geom_value, wkt_geom_srid