import json
import geojson
from shapely.geometry import shape

def from_geojson_to_wkt(geojson_obj:dict):
    a = json.dumps(geojson_obj)
    geo = geojson.loads(a)
    geom = shape(geo)

    return geom.wkt    