from rdflib import Graph
from rdflib.namespace import RDF, RDFS, SKOS, NamespaceManager
from rdflib import Graph, Namespace, URIRef, Literal, BNode
from rdflib.namespace import CSVW, DC, DCAT, DCTERMS, DOAP, FOAF, ODRL2, ORG, OWL, \
                           PROF, PROV, RDF, RDFS, SDO, SH, SKOS, SOSA, SSN, TIME, \
                           VOID, XSD
from uuid import uuid4


def create_landmark(landmark_uri:URIRef, label:str, lang:str, landmark_type:str, g:Graph, ont_namespace:Namespace, landmark_types_namespace:Namespace):
    g.add((landmark_uri, RDF.type, ont_namespace["Landmark"]))
    g.add((landmark_uri, ont_namespace["isLandmarkType"], landmark_types_namespace[landmark_type]))
    if label is not None:
        g.add((landmark_uri, RDFS.label, Literal(label, lang=lang)))

def create_event(event_uri:URIRef, g:Graph, ont_namespace:Namespace):
    g.add((event_uri, RDF.type, ont_namespace["Event"]))

def create_change(change_uri:URIRef, change_type:str, g:Graph, ont_namespace:Namespace, change_types_namespace:Namespace, change_class="Change"):
    g.add((change_uri, RDF.type, ont_namespace[change_class]))
    if change_type is not None:
        g.add((change_uri, ont_namespace["isChangeType"], change_types_namespace[change_type]))

def create_change_event_relation(change_uri:URIRef, event_uri:URIRef, g:Graph, ont_namespace:Namespace):
    g.add((change_uri, ont_namespace["dependsOn"], event_uri))

def create_attribute_change(change_uri:URIRef, attribute_uri:URIRef, g:Graph, ont_namespace:Namespace, change_types_namespace:Namespace):
    create_change(change_uri, None, g, ont_namespace, change_types_namespace, change_class="AttributeChange")
    g.add((change_uri, ont_namespace["appliedTo"], attribute_uri))

def create_landmark_change(change_uri:URIRef, change_type:str, landmark_uri:URIRef, g:Graph, ont_namespace:Namespace, change_types_namespace:Namespace):
    create_change(change_uri, change_type, g, ont_namespace, change_types_namespace, change_class="LandmarkChange")
    g.add((change_uri, ont_namespace["appliedTo"], landmark_uri))

def create_landmark_relation_change(change_uri:URIRef, change_type:str, landmark_uri:URIRef, g:Graph, ont_namespace:Namespace, change_types_namespace:Namespace):
    create_change(change_uri, change_type, g, ont_namespace, change_types_namespace, change_class="LandmarkRelationChange")
    g.add((change_uri, ont_namespace["appliedTo"], landmark_uri))

def create_landmark_with_changes(landmark_uri:URIRef, label:str, lang:str, landmark_type:str, g:Graph,
                                 ont_namespace:Namespace, elem_namespace:Namespace,
                                 landmark_types_namespace:Namespace, change_types_namespace:Namespace):
    create_landmark(landmark_uri, label, lang, landmark_type, g, ont_namespace, landmark_types_namespace)
    creation_change_uri, creation_event_uri = generate_uri(elem_namespace, "CH"), generate_uri(elem_namespace, "EV")
    dissolution_change_uri, dissolution_event_uri = generate_uri(elem_namespace, "CH"), generate_uri(elem_namespace, "EV")

    create_landmark_change(creation_change_uri, "LandmarkAppearance", landmark_uri, g, ont_namespace, change_types_namespace)
    create_landmark_change(dissolution_change_uri, "LandmarkDisappearance", landmark_uri, g, ont_namespace, change_types_namespace)
    create_event(creation_event_uri, g, ont_namespace)
    create_event(dissolution_event_uri, g, ont_namespace)
    create_change_event_relation(creation_change_uri, creation_event_uri, g, ont_namespace)
    create_change_event_relation(dissolution_change_uri, dissolution_event_uri, g, ont_namespace)

def create_landmark_attribute(attribute_uri:URIRef, landmark_uri:URIRef, attribute_type:str, g:Graph, ont_namespace:Namespace, attribute_types_namespace:Namespace):
    g.add((attribute_uri, RDF.type, ont_namespace["Attribute"]))
    g.add((attribute_uri, ont_namespace["isAttributeType"], attribute_types_namespace[attribute_type]))
    g.add((landmark_uri, ont_namespace["hasAttribute"], attribute_uri))

def create_attribute_version(attribute_uri:URIRef, value:str, g:Graph,
                             ont_namespace:Namespace, elem_namespace:Namespace, change_types_namespace:Namespace,
                             lang:str=None, datatype:URIRef=None, change_outdates_uri=None, change_makes_effective_uri=None):
    attr_vers_uri = generate_uri(elem_namespace, "AV")
    attr_vers_lit = Literal(value, lang=lang, datatype=datatype)

    g.add((attr_vers_uri, RDF.type, ont_namespace["AttributeVersion"]))
    g.add((attr_vers_uri, ont_namespace["versionValue"], attr_vers_lit))
    g.add((attribute_uri, ont_namespace["hasAttributeVersion"], attr_vers_uri))

    if change_makes_effective_uri is None:
        makes_effective_change_uri, makes_effective_event_uri = generate_uri(elem_namespace, "CH"), generate_uri(elem_namespace, "EV")
        create_attribute_change(makes_effective_change_uri, attribute_uri, g, ont_namespace, change_types_namespace)
        create_event(makes_effective_event_uri, g, ont_namespace)
        create_change_event_relation(makes_effective_change_uri, makes_effective_event_uri, g, ont_namespace)
    if change_outdates_uri is None:
        outdates_change_uri, outdates_event_uri = generate_uri(elem_namespace, "CH"), generate_uri(elem_namespace, "EV")
        create_attribute_change(outdates_change_uri, attribute_uri, g, ont_namespace, change_types_namespace)
        create_event(outdates_event_uri, g, ont_namespace)
        create_change_event_relation(outdates_change_uri, outdates_event_uri, g, ont_namespace)

    g.add((outdates_change_uri, ont_namespace["outdates"], attr_vers_uri))
    g.add((makes_effective_change_uri, ont_namespace["makesEffective"], attr_vers_uri))
    

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