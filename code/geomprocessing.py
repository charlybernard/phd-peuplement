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
    
    for feat in feature_collection.get("features"):
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

    new_geojson = {"type":"FeatureCollection", "features":new_geojson_features}

    return new_geojson