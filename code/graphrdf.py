from rdflib import Graph
from rdflib.namespace import RDF, RDFS, SKOS, NamespaceManager
from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import CSVW, DC, DCAT, DCTERMS, DOAP, FOAF, ODRL2, ORG, OWL, \
                           PROF, PROV, RDF, RDFS, SDO, SH, SKOS, SOSA, SSN, TIME, \
                           VOID, XSD
from uuid import uuid4


def create_landmark(g:Graph, landmark_uri:URIRef, label:str, lang:str, landmark_type:str, ont_namespace:Namespace, landmark_types_namespace:Namespace):
    g.add((landmark_uri, RDF.type, ont_namespace["Landmark"]))
    g.add((landmark_uri, ont_namespace["isLandmarkType"], landmark_types_namespace[landmark_type]))
    if label is not None:
        g.add((landmark_uri, RDFS.label, Literal(label, lang=lang)))

def create_landmark_relation(g:Graph, landmark_relation_uri:URIRef, locatum_uri:URIRef, relatum_uris:list[URIRef], landmark_relation_type:str, ont_namespace:Namespace, landmark_relation_types_namespace:Namespace):
    g.add((landmark_relation_uri, RDF.type, ont_namespace["LandmarkRelation"]))
    g.add((landmark_relation_uri, ont_namespace["isLandmarkRelationType"], landmark_relation_types_namespace[landmark_relation_type]))
    g.add((landmark_relation_uri, ont_namespace["locatum"], locatum_uri))
    for rel_uri in relatum_uris:
        g.add((landmark_relation_uri, ont_namespace["relatum"], rel_uri))

def create_event(g:Graph, event_uri:URIRef, ont_namespace:Namespace):
    g.add((event_uri, RDF.type, ont_namespace["Event"]))

def create_change(g:Graph, change_uri:URIRef, change_type:str, ont_namespace:Namespace, change_types_namespace:Namespace, change_class="Change"):
    g.add((change_uri, RDF.type, ont_namespace[change_class]))
    if change_type is not None:
        g.add((change_uri, ont_namespace["isChangeType"], change_types_namespace[change_type]))

def create_change_event_relation(g:Graph, change_uri:URIRef, event_uri:URIRef, ont_namespace:Namespace):
    g.add((change_uri, ont_namespace["dependsOn"], event_uri))

def create_attribute_change(g:Graph, change_uri:URIRef, attribute_uri:URIRef, ont_namespace:Namespace, change_types_namespace:Namespace):
    create_change(g, change_uri, None, ont_namespace, change_types_namespace, change_class="AttributeChange")
    g.add((change_uri, ont_namespace["appliedTo"], attribute_uri))

def create_landmark_change(g:Graph, change_uri:URIRef, change_type:str, landmark_uri:URIRef, ont_namespace:Namespace, change_types_namespace:Namespace):
    create_change(g, change_uri, change_type, ont_namespace, change_types_namespace, change_class="LandmarkChange")
    g.add((change_uri, ont_namespace["appliedTo"], landmark_uri))

def create_landmark_relation_change(g:Graph, change_uri:URIRef, change_type:str, landmark_uri:URIRef, ont_namespace:Namespace, change_types_namespace:Namespace):
    create_change(g, change_uri, change_type, ont_namespace, change_types_namespace, change_class="LandmarkRelationChange")
    g.add((change_uri, ont_namespace["appliedTo"], landmark_uri))

def create_landmark_with_changes(g:Graph,  landmark_uri:URIRef, label:str, lang:str, landmark_type:str,
                                 ont_namespace:Namespace, elem_namespace:Namespace,
                                 landmark_types_namespace:Namespace, change_types_namespace:Namespace):
    create_landmark(g, landmark_uri, label, lang, landmark_type, ont_namespace, landmark_types_namespace)
    creation_change_uri, creation_event_uri = generate_uri(elem_namespace, "CH"), generate_uri(elem_namespace, "EV")
    dissolution_change_uri, dissolution_event_uri = generate_uri(elem_namespace, "CH"), generate_uri(elem_namespace, "EV")

    create_landmark_change(g, creation_change_uri, "LandmarkAppearance", landmark_uri, ont_namespace, change_types_namespace)
    create_landmark_change(g, dissolution_change_uri, "LandmarkDisappearance", landmark_uri, ont_namespace, change_types_namespace)
    create_event(g, creation_event_uri, ont_namespace)
    create_event(g, dissolution_event_uri, ont_namespace)
    create_change_event_relation(g, creation_change_uri, creation_event_uri, ont_namespace)
    create_change_event_relation(g, dissolution_change_uri, dissolution_event_uri, ont_namespace)

def create_landmark_attribute(g:Graph, attribute_uri:URIRef, landmark_uri:URIRef, attribute_type:str, ont_namespace:Namespace, attribute_types_namespace:Namespace):
    g.add((attribute_uri, RDF.type, ont_namespace["Attribute"]))
    g.add((attribute_uri, ont_namespace["isAttributeType"], attribute_types_namespace[attribute_type]))
    g.add((landmark_uri, ont_namespace["hasAttribute"], attribute_uri))

def create_attribute_version(g:Graph, attribute_uri:URIRef, value:str,
                             ont_namespace:Namespace, elem_namespace:Namespace, change_types_namespace:Namespace,
                             lang:str=None, datatype:URIRef=None, change_outdates_uri=None, change_makes_effective_uri=None):
    attr_vers_uri = generate_uri(elem_namespace, "AV")
    attr_vers_lit = Literal(value, lang=lang, datatype=datatype)

    g.add((attr_vers_uri, RDF.type, ont_namespace["AttributeVersion"]))
    g.add((attr_vers_uri, ont_namespace["versionValue"], attr_vers_lit))
    g.add((attribute_uri, ont_namespace["hasAttributeVersion"], attr_vers_uri))

    if change_makes_effective_uri is None:
        makes_effective_change_uri, makes_effective_event_uri = generate_uri(elem_namespace, "CH"), generate_uri(elem_namespace, "EV")
        create_attribute_change(g, makes_effective_change_uri, attribute_uri, ont_namespace, change_types_namespace)
        create_event(g, makes_effective_event_uri, ont_namespace)
        create_change_event_relation(g, makes_effective_change_uri, makes_effective_event_uri, ont_namespace)
    if change_outdates_uri is None:
        outdates_change_uri, outdates_event_uri = generate_uri(elem_namespace, "CH"), generate_uri(elem_namespace, "EV")
        create_attribute_change(g, outdates_change_uri, attribute_uri, ont_namespace, change_types_namespace)
        create_event(g, outdates_event_uri, ont_namespace)
        create_change_event_relation(g, outdates_change_uri, outdates_event_uri, ont_namespace)

    g.add((outdates_change_uri, ont_namespace["outdates"], attr_vers_uri))
    g.add((makes_effective_change_uri, ont_namespace["makesEffective"], attr_vers_uri))
    
def create_crisp_time_instant(g:Graph, time_uri:URIRef, time_stamp:Literal, time_calendar:URIRef, time_precision:URIRef, ont_namespace:Namespace):
    g.add((time_uri, RDF.type, ont_namespace["CrispTimeInstant"]))
    g.add((time_uri, ont_namespace["timeStamp"], time_stamp))
    g.add((time_uri, ont_namespace["timeCalendar"], time_calendar))
    g.add((time_uri, ont_namespace["timePrecision"], time_precision))

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