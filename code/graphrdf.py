from rdflib import Graph
from rdflib.namespace import RDF, RDFS, SKOS, NamespaceManager
from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import CSVW, DC, DCAT, DCTERMS, DOAP, FOAF, ODRL2, ORG, OWL, \
                           PROF, PROV, RDF, RDFS, SDO, SH, SKOS, SOSA, SSN, TIME, \
                           VOID, XSD
from namespaces import NameSpaces
from uuid import uuid4
import re

np = NameSpaces()

def create_landmark(g:Graph, landmark_uri:URIRef, label:str, lang:str, landmark_type:URIRef):
    g.add((landmark_uri, RDF.type, np.ADDR["Landmark"]))
    g.add((landmark_uri, np.ADDR["isLandmarkType"], landmark_type))
    if label is not None:
        g.add((landmark_uri, RDFS.label, Literal(label, lang=lang)))

def create_landmark_relation(g:Graph, landmark_relation_uri:URIRef, locatum_uri:URIRef, relatum_uris:list[URIRef], landmark_relation_type:URIRef, is_address_segment=False, is_final_address_segment=False):
    lr_class = "LandmarkRelation"
    if is_final_address_segment:
        lr_class = "FinalAddressSegment"
    elif is_address_segment:
        lr_class = "AddressSegment"

    g.add((landmark_relation_uri, RDF.type, np.ADDR[lr_class]))
    g.add((landmark_relation_uri, np.ADDR["isLandmarkRelationType"], landmark_relation_type))
    g.add((landmark_relation_uri, np.ADDR["locatum"], locatum_uri))
    for rel_uri in relatum_uris:
        g.add((landmark_relation_uri, np.ADDR["relatum"], rel_uri))

def create_landmark_geometry(g:Graph, landmark_uri:URIRef, geom_wkt:str):
    geom_lit = Literal(geom_wkt, datatype=np.GEO.wktLiteral)
    g.add((landmark_uri, np.GEO.asWKT, geom_lit))

def create_landmark_insee(g:Graph, landmark_uri:URIRef, insee_num:str):
    insee_num_lit = Literal(insee_num)
    g.add((landmark_uri, np.GEOFLA.numInsee, insee_num_lit))

def add_provenance_to_resource(g:Graph, resource_uri:URIRef, prov_uri:URIRef):
    g.add((resource_uri, np.PROV.wasDerivedFrom, prov_uri))

def create_prov_entity(g:Graph, prov_uri:URIRef):
    g.add((prov_uri, RDF.type, np.PROV.Entity))

def create_address(g:Graph, address_uri:URIRef, address_label:str, address_lang:str, address_segments_list:list[URIRef], target_uri:URIRef):
    label_lit = Literal(address_label, lang=address_lang)
    g.add((address_uri, RDF.type, np.ADDR["Address"]))
    g.add((address_uri, RDFS.label, label_lit))
    g.add((address_uri, np.ADDR["targets"], target_uri))
    g.add((address_uri, np.ADDR["firstStep"], address_segments_list[0]))

    prev_addr_seg = address_segments_list[0]
    for addr_seg in address_segments_list[1:]:
        g.add((prev_addr_seg, np.ADDR["nextStep"], addr_seg))
        prev_addr_seg = addr_seg

def create_event(g:Graph, event_uri:URIRef):
    g.add((event_uri, RDF.type, np.ADDR["Event"]))

def create_change(g:Graph, change_uri:URIRef, change_type:URIRef, change_class="Change"):
    g.add((change_uri, RDF.type, np.ADDR[change_class]))
    if change_type is not None:
        g.add((change_uri, np.ADDR["isChangeType"], change_type))

def create_change_event_relation(g:Graph, change_uri:URIRef, event_uri:URIRef):
    g.add((change_uri, np.ADDR["dependsOn"], event_uri))

def create_attribute_change(g:Graph, change_uri:URIRef, attribute_uri:URIRef):
    create_change(g, change_uri, None, change_class="AttributeChange")
    g.add((change_uri, np.ADDR["appliedTo"], attribute_uri))

def create_landmark_change(g:Graph, change_uri:URIRef, change_type:URIRef, landmark_uri:URIRef):
    create_change(g, change_uri, change_type, change_class="LandmarkChange")
    g.add((change_uri, np.ADDR["appliedTo"], landmark_uri))

def create_landmark_relation_change(g:Graph, change_uri:URIRef, change_type:URIRef, landmark_uri:URIRef):
    create_change(g, change_uri, change_type, change_class="LandmarkRelationChange")
    g.add((change_uri, np.ADDR["appliedTo"], landmark_uri))

def create_landmark_with_changes(g:Graph,  landmark_uri:URIRef, label:str, lang:str, landmark_type:URIRef,
                                resource_namespace:Namespace):
    create_landmark(g, landmark_uri, label, lang, landmark_type, np.ADDR)
    creation_change_uri, creation_event_uri = generate_uri(resource_namespace, "CH"), generate_uri(resource_namespace, "EV")
    dissolution_change_uri, dissolution_event_uri = generate_uri(resource_namespace, "CH"), generate_uri(resource_namespace, "EV")

    change_type_landmark_appearance = np.CTYPE["LandmarkAppearance"]
    change_type_landmark_disappearance = np.CTYPE["LandmarkDisappearance"]
    create_landmark_change(g, creation_change_uri, change_type_landmark_appearance, landmark_uri)
    create_landmark_change(g, dissolution_change_uri,change_type_landmark_disappearance, landmark_uri)
    create_event(g, creation_event_uri)
    create_event(g, dissolution_event_uri)
    create_change_event_relation(g, creation_change_uri, creation_event_uri)
    create_change_event_relation(g, dissolution_change_uri, dissolution_event_uri)

def create_landmark_attribute(g:Graph, attribute_uri:URIRef, landmark_uri:URIRef, attribute_type:URIRef):
    g.add((attribute_uri, RDF.type, np.ADDR["Attribute"]))
    g.add((attribute_uri, np.ADDR["isAttributeType"], attribute_type))
    g.add((landmark_uri, np.ADDR["hasAttribute"], attribute_uri))

def create_attribute_version(g:Graph, attribute_uri:URIRef, value:str, resource_namespace:Namespace,
                             lang:str=None, datatype:URIRef=None, change_outdates_uri=None, change_makes_effective_uri=None):
    attr_vers_uri = generate_uri(resource_namespace, "AV")
    attr_vers_lit = Literal(value, lang=lang, datatype=datatype)

    g.add((attr_vers_uri, RDF.type, np.ADDR["AttributeVersion"]))
    g.add((attr_vers_uri, np.ADDR["versionValue"], attr_vers_lit))
    g.add((attribute_uri, np.ADDR["hasAttributeVersion"], attr_vers_uri))

    if change_makes_effective_uri is None:
        makes_effective_change_uri, makes_effective_event_uri = generate_uri(resource_namespace, "CH"), generate_uri(resource_namespace, "EV")
        create_attribute_change(g, makes_effective_change_uri, attribute_uri)
        create_event(g, makes_effective_event_uri)
        create_change_event_relation(g, makes_effective_change_uri, makes_effective_event_uri)
    if change_outdates_uri is None:
        outdates_change_uri, outdates_event_uri = generate_uri(resource_namespace, "CH"), generate_uri(resource_namespace, "EV")
        create_attribute_change(g, outdates_change_uri, attribute_uri)
        create_event(g, outdates_event_uri)
        create_change_event_relation(g, outdates_change_uri, outdates_event_uri)

    g.add((outdates_change_uri, np.ADDR["outdates"], attr_vers_uri))
    g.add((makes_effective_change_uri, np.ADDR["makesEffective"], attr_vers_uri))
    
def create_crisp_time_instant(g:Graph, time_uri:URIRef, time_stamp:Literal, time_calendar:URIRef, time_precision:URIRef):
    g.add((time_uri, RDF.type, np.ADDR["CrispTimeInstant"]))
    g.add((time_uri, np.ADDR["timeStamp"], time_stamp))
    g.add((time_uri, np.ADDR["timeCalendar"], time_calendar))
    g.add((time_uri, np.ADDR["timePrecision"], time_precision))

def convert_result_elem_to_rdflib_elem(result_elem:dict):
    """
    À partir d'un dictionnaire qui décrit un élement d'un résultat d'une requête, le convertir en un élément d'un triplet d'un graph (URIRef, Literal, Bnode)
    """
    
    res_type = result_elem.get("type")
    res_value = result_elem.get("value")
    
    if res_type == "uri":
        return URIRef(res_value)
    elif res_type == "literal":
        res_lang = result_elem.get("xml:lang")
        res_datatype = result_elem.get("datatype")
        return Literal(res_value, lang=res_lang, datatype=res_datatype)
    elif res_type == "bnode":
        return BNode(res_value)
    
def generate_uri(namespace:Namespace=None, prefix:str=None):
    if prefix:
        return namespace[f"{prefix}_{uuid4().hex}"]
    else:
        return namespace[uuid4().hex]
    
def generate_uuid():
    return uuid4().hex

def add_namespaces_to_graph(g:Graph, namespaces:dict):
    for prefix, namespace in namespaces.items():
        g.bind(prefix, namespace)

def is_valid_uri(uri_str:str):
    regex = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return uri_str is not None and regex.search(uri_str)

def get_valid_uri(uri_str:str):
    if is_valid_uri(uri_str):
        return URIRef(uri_str)
    else:
        return None
