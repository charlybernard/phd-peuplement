import os
import datetime
from rdflib import Graph, Namespace, Literal, BNode, URIRef, XSD
from rdflib.namespace import RDF
import strprocessing as sp
import ontorefine as otr
import graphdb as gd
import curl as curl

def get_facts_implicit_triples(graphdb_url, repository_name, ttl_file:str, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef, tmp_named_graph_uri:URIRef):
    """
    All interesting triples (according the predicate of the triples) have been stored in a temporary named graph...
    Get triples whose :
    * subjects are resources named RS which are defined in facts named graph (it exists `<RS a ?rtype>` in facts named graph) 
    * objects are not resources named RO which are definned in factoids named graph (those such as it does't exist <RO a ?rtype> factoids named graph)
    """
    
    query = f"""
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

    CONSTRUCT {{
        ?s ?p ?o
    }}
    WHERE {{
        BIND ({facts_named_graph_uri.n3()} AS ?gf)
        BIND ({factoids_named_graph_uri.n3()} AS ?gs)
        BIND ({tmp_named_graph_uri.n3()} AS ?gt)

        GRAPH ?gt {{
            ?s ?p ?o.
        }}

        GRAPH ?gf {{
            ?s a ?sType.
        }}

        OPTIONAL {{
            GRAPH ?g {{?o a ?oType}}
        }}

        BIND(isIRI(?o) AS ?isIRI)
        BIND(IF(BOUND(?g) && ?g != ?gs, "true"^^xsd:boolean, "false"^^xsd:boolean) AS ?iriInFacts)
        FILTER(?isIRI = "false"^^xsd:boolean || ?iriInFacts = "true"^^xsd:boolean)
    }}
    """

    gd.construct_query_to_ttl(query, graphdb_url, repository_name, ttl_file)

def transfer_facts_implicit_triples(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef, tmp_named_graph_uri:URIRef):
    """
    All interesting triples (according the predicate of the triples) have been stored in a temporary named graph..
    Transfer triplet whose :
    * subjects are resources named RS which are defined in facts named graph (it exists `<RS a ?rtype>` in facts named graph) 
    * objects are not resources named RO which are definned in factoids named graph (those such as it does't exist <RO a ?rtype> factoids named graph)
    """
    
    query = f"""
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

    DELETE {{
        GRAPH ?gt {{
            ?s ?p ?o.
        }}
    }}
    INSERT {{
        GRAPH ?gf {{
            ?s ?p ?o.
        }}
    }}
    WHERE {{
        BIND ({facts_named_graph_uri.n3()} AS ?gf)
        BIND ({factoids_named_graph_uri.n3()} AS ?gs)
        BIND ({tmp_named_graph_uri.n3()} AS ?gt)

        GRAPH ?gt {{
            ?s ?p ?o.
        }}

        GRAPH ?gf {{
            ?s a ?sType.
        }}

        OPTIONAL {{
            GRAPH ?g {{?o a ?oType}}
        }}

        BIND(isIRI(?o) AS ?isIRI)
        BIND(IF(BOUND(?g) && ?g != ?gs, "true"^^xsd:boolean, "false"^^xsd:boolean) AS ?iriInFacts)
        FILTER(?isIRI = "false"^^xsd:boolean || ?iriInFacts = "true"^^xsd:boolean)
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def add_normalized_label_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri:URIRef):
    """
    This function normalizes label according some rules :
    * get only low cases ;
    * remove diacritics (accents, cedillas...)
    * remove "useless" words : determiners, prepositions...
    * theses normalized labels are related to resources via `skos:hiddenLabel`
    """

    label_var = "?label"
    norm_label_var = "?normLabel"
    norm_label_function = sp.get_lower_simplified_french_street_name_function(label_var)

    prefixes = """
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX atype: <http://rdf.geohistoricaldata.org/id/codes/address/attributeType/>
    """

    query = prefixes + f"""
    INSERT {{
        GRAPH ?g {{
            ?landmark skos:hiddenLabel {norm_label_var}.
        }}
    }}
    WHERE {{
        BIND({factoids_named_graph_uri.n3()} AS ?g)
        GRAPH ?g {{
            {{
                ?landmark a addr:Landmark ; addr:hasAttribute [a addr:Attribute ; addr:isAttributeType atype:Name ; addr:hasAttributeVersion [a addr:AttributeVersion ; addr:versionValue {label_var}]].
            }} UNION {{
                ?landmark a addr:Landmark ; rdfs:label {label_var} .
            }} UNION {{
                ?landmark a addr:Landmark ; skos:altLabel {label_var} .
            }}
            BIND(REPLACE({norm_label_function}, " ", "") AS {norm_label_var})
        }}
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def get_time_instant_elements(time_dict:dict):
    if time_dict is None:
        return [None, None, None]

    time_namespace = Namespace("http://www.w3.org/2006/time#")
    wd_namespace = Namespace("http://www.wikidata.org/entity/")

    time_units = {
        "day": time_namespace["unitDay"],
        "month": time_namespace["unitMonth"],
        "year": time_namespace["unitYear"],
        "decade": time_namespace["unitDecade"],
        "century": time_namespace["unitCentury"],
        "millenium": time_namespace["unitMillenium"]
    }

    time_calendars = {
        "gregorian": wd_namespace["Q1985727"],
        "republican": wd_namespace["Q181974"]
    }
    time_stamp = time_dict.get("stamp")
    time_cal = time_dict.get("calendar")
    time_prec = time_dict.get("precision")
    
    stamp = Literal(time_stamp, datatype=XSD.dateTimeStamp)

    precision = time_units.get(time_prec)
    calendar = time_calendars.get(time_cal)

    return [stamp, precision, calendar]


def create_time_resources_for_current_sources(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, time_description:dict={}):
    """
    Ajout de ressources temporelles pour des sources décrivant des données actuelles
    """

    stamp_key, precision_key, calendar_key = "stamp", "precision", "calendar"
    start_time_key, end_time_key = "start_time", "end_time"
    start_time = get_time_instant_elements(time_description.get(start_time_key))
    end_time = get_time_instant_elements(time_description.get("end_time"))

    if start_time is None or None in start_time:
        time_description[start_time_key] = {stamp_key:datetime.datetime.now().isoformat(), precision_key:"day", calendar_key:"gregorian"}

    if end_time is None or None in end_time:
        time_description[end_time_key] = {stamp_key:datetime.datetime.now().isoformat(), precision_key:"day", calendar_key:"gregorian"}
        
    create_time_resources(graphdb_url, repository_name, factoids_named_graph_uri, time_description)

def create_time_resources(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, time_description:dict):
    """
    À partir de la variable `geojson_time` qui décrit un intervalle temporel de validité des données de la source, ajouter des instants temporels flous à tous les événements :
    - pour les événements liés à des changements d'apparition, on considère qu'ils sont liés à un instant qui indique la date au plus tard (hasLatestTimeInstant)
    - pour les événements liés à des changements de disparition, on considère qu'ils sont liés à un instant qui indique la date au plus tôt (hasEarliestTimeInstant)

    Si les dates de début et / ou de fin ne sont pas fournies, la fonction ne crée pas d'instant
    """
    
    prefixes = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>
    PREFIX geofla: <http://data.ign.fr/def/geofla#>
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX ltype: <http://rdf.geohistoricaldata.org/id/codes/address/landmarkType/>
    """

    start_time = get_time_instant_elements(time_description.get("start_time"))
    end_time = get_time_instant_elements(time_description.get("end_time"))

    add_time_instants_for_timeless_events(graphdb_url, repository_name, factoids_named_graph_uri, "start", start_time[0], start_time[1], start_time[2])
    add_time_instants_for_timeless_events(graphdb_url, repository_name, factoids_named_graph_uri, "end", end_time[0], end_time[1], end_time[2])


def add_time_instants_for_timeless_events(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, time_type:str, stamp:Literal, precision:URIRef, calendar:URIRef):
    if None in [stamp, precision, calendar]:
        return None
    
    if time_type == "start":
        time_predicate = ":hasLatestTimeInstant"
        change_types = ["ctype:AttributeVersionAppearance", "ctype:LandmarkAppearance", "ctype:LandmarkRelationAppearance"]
    elif time_type == "end":
        time_predicate = ":hasEarliestTimeInstant"
        change_types = ["ctype:AttributeVersionDisappearance", "ctype:LandmarkDisappearance", "ctype:LandmarkRelationDisappearance"]
    else:
        return None
    
    change_types_filter = ", ".join(change_types)

    query = f"""
    PREFIX : <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX ctype: <http://rdf.geohistoricaldata.org/id/codes/address/changeType/>
    PREFIX factoids: <http://rdf.geohistoricaldata.org/id/address/factoids/>

    INSERT {{
        GRAPH {factoids_named_graph_uri.n3()} {{
            ?ev {time_predicate} ?timeInstant.
            ?timeInstant a :CrispTimeInstant; :timeStamp {stamp.n3()} ; :timePrecision {precision.n3()} ; :timeCalendar {calendar.n3()}.
        }}
    }}
    WHERE {{
        {{
            SELECT DISTINCT ?ev
            WHERE {{
                ?cg a :Change; :isChangeType ?cgType; :dependsOn ?ev.
                MINUS {{ ?ev :hasTime ?t }}
                FILTER(?cgType IN ({change_types_filter}))
            }}
        }}
        BIND(URI(CONCAT(STR(URI(factoids:)), "TI_", STRUUID())) AS ?timeInstant)
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def remove_time_instant_without_timestamp(graphdb_url, repository_name):
    """
    It exists some resources whose class is `addr:TimeInstant` without any timestamp. They must be removed as they are useless.
    """
    query = f"""
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>

    DELETE {{
        ?timeInstant ?p ?o.
        ?s ?p ?timeInstant.
    }}
    WHERE {{
        ?timeInstant a addr:TimeInstant.
        MINUS {{?timeInstant addr:timeStamp ?timeStamp}}
        {{?timeInstant ?p ?o}}UNION{{?s ?p ?timeInstant}}
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def transfert_immutable_triples(graphdb_url, repository_name, factoids_named_graph_uri, permanent_named_graph_uri):
    """
    All created triples via Ontotext-Refine are initially imported in factoids named graph.
    Some of them must be transfered in a permanent named graph, as they must not be modified while importing them in facts repository.
    """

    prefixes = """
    PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>
    PREFIX prov: <http://www.w3.org/ns/prov#>
    PREFIX wb: <http://wikiba.se/ontology#>
    """ 
    
    # All triples whose predicate is `rico:isOrWasDescribedBy` are moved to permanent named graph
    query1 = prefixes + f"""
    DELETE {{
       ?s ?p ?o
    }}
    INSERT {{
        GRAPH {permanent_named_graph_uri.n3()} {{
            ?s ?p ?o.
        }}
    }}
    WHERE {{
        BIND(rico:isOrWasDescribedBy AS ?p)
        ?s ?p ?o.
    }} ; 
    """

    # All triples whose subject is an URI and is a object of a triples whose predicate is `prov:wasDerivedFrom` are moved to permanent named graph
    query2 = prefixes + f"""
    DELETE {{
        GRAPH ?gf {{ ?prov ?p ?o }}
    }}
    INSERT {{
        GRAPH ?gp {{ ?prov ?p ?o }}
    }}
    WHERE
    {{
        BIND({factoids_named_graph_uri.n3()} AS ?gf)
        BIND({permanent_named_graph_uri.n3()} AS ?gp)
        GRAPH ?gf {{ 
            ?elem prov:wasDerivedFrom ?prov.
            ?prov ?p ?o.
        }}
    }}
    """

    # All triples whose subject is a Wikibase Item or Statement are moved to permanent named graph
    query3 = prefixes + f"""
    DELETE {{
        GRAPH ?gf {{ ?elem a ?type }}
    }}
    INSERT {{
        GRAPH ?gp {{ ?elem a ?type }}
    }}
    WHERE
    {{
        BIND({factoids_named_graph_uri.n3()} AS ?gf)
        BIND({permanent_named_graph_uri.n3()} AS ?gp)
        GRAPH ?gf {{ 
            ?elem a ?type.
        }}
        FILTER (?type in (wb:Item, wb:Statement))
    }}
    """

    queries = [query1, query2, query3]
    for query in queries:
        gd.update_query(query, graphdb_url, repository_name)

def add_factoids_resources_links(graphdb_url, repository_name, factoids_named_graph_uri:URIRef):
    """
    A factoid is the representation of an information, of a fact in a source.
    Landmarks which have an identity in a source are created and must have a link with the source to attest provenance of its existence.
    
    To do that, all landmarks (`?landmark`) in factoids named (`factoids_named_graph_uri`) graph are selected to create this triple : `<?landmark rico:isOrWasDescribedBy ?sourceUri>`.
    `?sourceUri` est the URI which describes the source.
    """

    prefixes = """
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX prov: <http://www.w3.org/ns/prov#>
    """

    # Ajouter le lien de provenance des versions d'attributs
    query = prefixes + f"""
    INSERT {{
        GRAPH {factoids_named_graph_uri.n3()} {{
            ?attrVers ?p ?prov.
        }}
    }}
    WHERE {{
        BIND(prov:wasDerivedFrom AS ?p)
        ?lm a addr:Landmark ; addr:hasAttribute [addr:hasAttributeVersion ?attrVers] ; ?p ?prov.
    }} ; 
    """

    gd.update_query(query, graphdb_url, repository_name)

def create_factoid_repository(graphdb_url, repository_name, namespace_prefixes, tmp_folder, ont_file, ontology_named_graph_name, ruleset_file=None, disable_same_as=False, clear_if_exists=False):
    """
    Initialisation of a repository to create a factoids graph

    `clear_if_exists` is a bool to remove all statements if repository already exists"
    """

    local_config_file_name = f"config_for_{repository_name}.ttl" 
    local_config_file = os.path.join(tmp_folder, local_config_file_name)

    if ruleset_file is not None:
        gd.create_config_local_repository_file(local_config_file, repository_name, ruleset_file=ruleset_file, disable_same_as=disable_same_as)
    else:
        gd.create_config_local_repository_file(local_config_file, repository_name, disable_same_as=disable_same_as)
    gd.create_repository_from_config_file(graphdb_url, local_config_file)
    if clear_if_exists:
        gd.clear_repository(graphdb_url, repository_name)

    gd.add_prefixes_to_repository(graphdb_url, repository_name, namespace_prefixes)
    gd.import_ttl_file_in_graphdb(graphdb_url, repository_name, ont_file, ontology_named_graph_name)

def transfert_factoids_to_facts_repository(graphdb_url, facts_repository_name, factoids_repository_name, factoids_ttl_file, permanent_ttl_file, factoids_named_graph_name, facts_named_graph_name, permanent_named_graph_name):
    """
    Transfer factoids to facts graph
    """

    factoids_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, factoids_repository_name, factoids_named_graph_name))
    permanent_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, factoids_repository_name, permanent_named_graph_name))
    gd.export_data_from_repository(graphdb_url, factoids_repository_name, factoids_ttl_file, factoids_named_graph_uri)
    gd.export_data_from_repository(graphdb_url, factoids_repository_name, permanent_ttl_file, permanent_named_graph_uri)
    gd.import_ttl_file_in_graphdb(graphdb_url, facts_repository_name, factoids_ttl_file, factoids_named_graph_name)
    gd.import_ttl_file_in_graphdb(graphdb_url, facts_repository_name, permanent_ttl_file, facts_named_graph_name)

def from_raw_to_data_to_graphdb(graphdb_url, ontorefine_url, ontorefine_cmd, repository_name, named_graph_name, csv_file, ontorefine_mapping_file, kg_file):
    """
    Converting the raw file to the graph in GraphDB

    From a raw file (a tabular file such as a CSV), the function converts it into a knowledge graph in a ttl file (here kg_file).
    The way in which the file is converted is defined by the ontorefine_mapping_file, and the conversion is carried out by Ontotext Refine.
    The ttl file is then imported into the repository_name directory, and more specifically into the graph named `graph_name`.   
    """

    # Si ça ne marche pas ici, c'est sûrement qu'Ontotext Refine n'est pas lancé
    otr.get_export_file_from_ontorefine(csv_file, ontorefine_mapping_file, kg_file, ontorefine_cmd, ontorefine_url, repository_name)

    # Importer le fichier `kg_file` qui a été créé lors de la ligne précédente dans le répertoire `repository_name`, dans le graphe nommé `graph_name` 
    gd.import_ttl_file_in_graphdb(graphdb_url, repository_name, kg_file, named_graph_name)

def create_unlinked_resources(graphdb_url, repository_name, refactoids_class:URIRef, refactoids_prefix:str, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
    """
    Create resources as facts and create a provenance link for each one
    """

    query = f"""
    PREFIX facts: <http://rdf.geohistoricaldata.org/id/address/facts/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>

    INSERT {{
        GRAPH {facts_named_graph_uri.n3()} {{
            ?resource a ?type.
        }}
        GRAPH {factoids_named_graph_uri.n3()} {{
            ?resource owl:sameAs ?sourceResource.
        }}
    }}
    WHERE {{
        ?type rdfs:subClassOf* {refactoids_class.n3()}.
        GRAPH {factoids_named_graph_uri.n3()} {{
            ?sourceResource a ?type.
        }}
        MINUS {{
            ?fact a {refactoids_class.n3()} ; owl:sameAs ?sourceResource. 
            FILTER(?fact != ?sourceResource)
        }}
        BIND(URI(CONCAT(STR(URI(facts:)), "{refactoids_prefix}_", STRUUID())) AS ?resource)
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def create_same_as_links_between_landmarks(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
    """
    Create `owl:sameAs` links between similar landmarks.
    """

    create_same_as_links_between_areas(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)
    create_same_as_links_between_thoroughfares(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)
    create_same_as_links_between_housenumbers(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)

def create_same_as_links_between_areas(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
    """
    Pour les repères de type DISTRICT ou CITY définis dans le graphe nommé `factoids_named_graph_uri`, les lier avec un repère de même type défini dans `facts_named_graph_uri` s'ils ont un nom similaire.
    Le lien créé est mis dans `factoids_facts_named_graph_uri`.
    """

    prefixes = """
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX ltype: <http://rdf.geohistoricaldata.org/id/codes/address/landmarkType/>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    """

    query = prefixes + f"""
    INSERT {{
        GRAPH {factoids_named_graph_uri.n3()} {{
            ?factsLandmark owl:sameAs ?sourceLandmark.
        }}
    }}
    WHERE {{
        GRAPH {factoids_named_graph_uri.n3()} {{
            ?sourceLandmark a addr:Landmark ; addr:isLandmarkType ?landmarkType ; addr:hasAttribute ?sourceLandmarkAttr.
            ?sourceLandmarkAttr addr:isAttributeType ?attrType ; addr:hasAttributeVersion [addr:versionValue ?versionValue].
        }}
        GRAPH {facts_named_graph_uri.n3()} {{
            ?factsLandmark a addr:Landmark ; addr:isLandmarkType ?landmarkType ; addr:hasAttribute ?factsLandmarkAttr.
            ?factsLandmarkAttr addr:isAttributeType ?attrType ; addr:hasAttributeVersion [addr:versionValue ?versionValue].
           }}
        FILTER (?landmarkType IN (ltype:District, ltype:City, ltype:PostalCode))
        MINUS {{?factsLandmark owl:sameAs ?sourceLandmark}}
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def create_same_as_links_between_thoroughfares(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
    """
    Pour les repères de type VOIE définis dans le graphe nommé `factoids_named_graph_uri`, les lier avec un repère de même type défini dans `facts_named_graph_uri` s'ils ont un nom similaire.
    Le lien créé est mis dans `factoids_facts_named_graph_uri`.
    """

    prefixes = """
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX ltype: <http://rdf.geohistoricaldata.org/id/codes/address/landmarkType/>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    """

    query = prefixes + f"""
    INSERT {{
        GRAPH {factoids_named_graph_uri.n3()} {{
            ?factsLandmark owl:sameAs ?sourceLandmark.
        }}
    }}
    WHERE {{
        GRAPH {factoids_named_graph_uri.n3()} {{
            ?sourceLandmark a addr:Landmark ; addr:isLandmarkType ltype:Thoroughfare.
        }}
        GRAPH {facts_named_graph_uri.n3()} {{
            ?factsLandmark a addr:Landmark ; addr:isLandmarkType ltype:Thoroughfare.
           }}
        MINUS {{?factsLandmark owl:sameAs ?sourceLandmark}}
        ?sourceLandmark skos:hiddenLabel ?label.
        ?factsLandmark skos:hiddenLabel ?label.
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)


def create_same_as_links_between_housenumbers(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
    """
    Pour les repères de type HOUSENUMBER définis dans le graphe nommé `factoids_named_graph_uri`, les lier avec un repère de même type défini dans `facts_named_graph_uri` s'ils ont un nom similaire.
    Le lien créé est mis dans `factoids_facts_named_graph_uri`.
    """

    prefixes = """
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX ltype: <http://rdf.geohistoricaldata.org/id/codes/address/landmarkType/>
    PREFIX lrtype: <http://rdf.geohistoricaldata.org/id/codes/address/landmarkRelationType/>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    """

    query = prefixes + f"""
    INSERT {{
        GRAPH {factoids_named_graph_uri.n3()} {{
            ?factsHN owl:sameAs ?sourceHN.
        }}
    }}
    WHERE {{
        BIND(ltype:HouseNumber AS ?landmarkType)
        BIND(lrtype:Along AS ?landmarkRelationType)
        GRAPH {factoids_named_graph_uri.n3()} {{
            ?sourceHN a addr:Landmark ; addr:isLandmarkType ?landmarkType.
        }}
        GRAPH {facts_named_graph_uri.n3()} {{
            ?factsHN a addr:Landmark ; addr:isLandmarkType ?landmarkType.
           }}

        ?sourceLR a addr:LandmarkRelation ; addr:isLandmarkRelationType ?landmarkRelationType ; addr:locatum ?sourceHN ; addr:relatum ?thoroughfare.
        ?factsLR a addr:LandmarkRelation ; addr:isLandmarkRelationType ?landmarkRelationType ; addr:locatum ?factsHN ; addr:relatum ?thoroughfare.
        MINUS {{?factsHN owl:sameAs ?sourceHN}}
        ?sourceHN skos:hiddenLabel ?label.
        ?factsHN skos:hiddenLabel ?label.
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def create_same_as_links_between_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
    """
    Pour des relations entre repères dans le graphe nommé `factoids_named_graph_uri`, les lier avec une relation entre repères dans `facts_named_graph_uri` qui sont similaires (mêmes locatum, relatums et type de relation).
    Le lien créé est mis dans `factoids_facts_named_graph_uri`.
    """

    prefixes = """
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    """

    query = prefixes + f"""
    INSERT {{
        GRAPH {factoids_named_graph_uri.n3()} {{ ?lr1 owl:sameAs ?lr2. }}
    }}
    WHERE {{
        GRAPH {facts_named_graph_uri.n3()} {{ ?lr1 a ?typeLR1. }}
        GRAPH {factoids_named_graph_uri.n3()} {{ ?lr2 a ?typeLR2. }}
        ?typeLR1 rdfs:subClassOf addr:LandmarkRelation.
        ?typeLR2 rdfs:subClassOf addr:LandmarkRelation.
        ?lr1 addr:isLandmarkRelationType ?lrt ; addr:locatum ?l.
        ?lr2 addr:isLandmarkRelationType ?lrt ; addr:locatum ?l.
        MINUS
        {{
            SELECT DISTINCT ?lr1 ?lr2 WHERE {{
                ?lr1 addr:isLandmarkRelationType ?lrt ; addr:locatum ?l.
                ?lr2 addr:isLandmarkRelationType ?lrt ; addr:locatum ?l.
                ?lr1 addr:relatum ?r.
                MINUS {{
                    ?lr2 addr:relatum ?r.
                }}
            }}
        }}
        MINUS
        {{
            SELECT DISTINCT ?lr1 ?lr2 WHERE {{
                ?lr1 addr:isLandmarkRelationType ?lrt ; addr:locatum ?l.
                ?lr2 addr:isLandmarkRelationType ?lrt ; addr:locatum ?l.
                ?lr2 addr:relatum ?r.
                MINUS {{
                    ?lr1 addr:relatum ?r.
                }}
            }}
        }}  
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def store_interesting_implicit_triples(graphdb_url, repository_name, tmp_named_graph_uri:URIRef):
    query = f"""
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX facts: <http://rdf.geohistoricaldata.org/id/address/facts/>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>
    PREFIX prov: <http://www.w3.org/ns/prov#>
    
    INSERT {{
        GRAPH {tmp_named_graph_uri.n3()} {{
            ?s ?p ?o.
        }}
    }}
    WHERE {{
        ?s ?p ?o.

        MINUS {{
            GRAPH ?g {{ ?s ?p ?o. }}
        }}
        FILTER(?p in (addr:isAttributeType,addr:isChangeType,addr:isLandmarkType,addr:isLandmarkRelationType,
            addr:hasTime,addr:hasEarliestTimeInstant,addr:hasLatestTimeInstant,
            addr:timeCalendar,addr:timePrecision,addr:timeStamp,
            addr:hasAttribute,addr:hasAttributeVersion,addr:versionValue,addr:appliedTo,addr:dependsOn,addr:makesEffective,addr:outdates,
            addr:targets,addr:locatum,addr:relatum,addr:firstStep,addr:nextStep,
            rdfs:label,skos:hiddenLabel,skos:closeMatch,rico:isOrWasDescribedBy,prov:wasDerivedFrom
        ))
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def transfer_implicit_triples(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef, tmp_named_graph_uri:URIRef, implicit_to_facts_ttl_file:str):
    # Refaire les inférences pour forcer certaines mises à jour
    # Éviter que certains triplets implicites "prennent le dessus" sur des triplets explicites
    gd.reinfer_repository(graphdb_url, repository_name)

    # On stocke dans un graphe nommé temporaire les triplets implicites qui sont intéressants (selon la propriété du triplet)
    store_interesting_implicit_triples(graphdb_url, repository_name, tmp_named_graph_uri)

    # # # Suppression des liens owl:sameAs pour casser les liens implicites qui ont été stockés explicitement dans le graphe nommé
    # gd.remove_all_same_as_triples(graphdb_url, repository_name)
    
    # Récupérer dans un ficher TTL temporaire les triplets stockés dans le graphe nommé temporaire qui ne sont pas liés aux factoïdes
    get_facts_implicit_triples(graphdb_url,repository_name, implicit_to_facts_ttl_file, factoids_named_graph_uri, facts_named_graph_uri, tmp_named_graph_uri)

    # Suppression du graphe nommé temporaire
    gd.remove_named_graph_from_uri(tmp_named_graph_uri)

    # Importer du fichier TTL dans le graphe nommé des faits
    gd.import_ttl_file_in_graphdb(graphdb_url, repository_name, implicit_to_facts_ttl_file, named_graph_uri=facts_named_graph_uri)

def links_factoids_with_facts(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
    """
    Landmarks are created as follows:
        * creation of links (using `owl:sameAs`) between landmarks in the facts named graph and those which are in the factoid named graph ;
        * using inference rules, new `owl:sameAs` links are deduced
        * for each resource defined in the factoids, we check whether it exists in the fact graph (if it is linked with a `owl:sameAs` to a resource in the fact graph)
        * for unlinked factoid resources, we create its equivalent in the fact graph
    """

    create_same_as_links_between_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)
    create_same_as_links_between_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)

    addr_ns = Namespace("http://rdf.geohistoricaldata.org/def/address#")

    resource_classes = {"LM": addr_ns["Landmark"], "LR": addr_ns["LandmarkRelation"], "ADDR": addr_ns["Address"],
                        "ATTR": addr_ns["Attribute"], "AV":addr_ns["AttributeVersion"], "CG": addr_ns["Change"], "EV":addr_ns["Event"], "TE": addr_ns["TemporalEntity"]}

    for prefix, class_name in resource_classes.items():
        create_unlinked_resources(graphdb_url, repository_name, class_name, prefix, factoids_named_graph_uri, facts_named_graph_uri)

def import_factoids_in_facts(graphdb_url, repository_name, factoids_named_graph_name, facts_named_graph_name, tmp_named_graph_name, facts_ttl_file, implicit_to_facts_ttl_file, ont_file, ontology_named_graph_name):
    """
    Factoids are imported into the fact graph in three steps:
        * linking the elements of the factoid graph with the factoid graph (`links_factoids_with_facts()`)
        * With the previous step, inferences are made and `transfer_implicit_triples()` recovers the interesting implicit triples to make them explicit by putting them in the fact graph.
        * `export_named_graph_and_reload_repository()` exports the fact graph to a temporary file in order to clean up the directory (deleting unnecessary implicit triples), the fact graph is reloaded into the directory.
    """

    facts_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, facts_named_graph_name))
    factoids_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, factoids_named_graph_name))
    tmp_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, tmp_named_graph_name))

    links_factoids_with_facts(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)

    # # After having matched some factoids with facts, rules can deduce some new links, this function does that.
    # create_same_as_links_from_queries(graphdb_url, repository_name)

    # Refaire les inférences pour supprimer notamment les liens owl:sameAs implicites qui ne sont pas supprimés
    gd.reinfer_repository(graphdb_url, repository_name)
    
    # Transférer les triplets implicites intéressants dans le graphe nommé des faits
    transfer_implicit_triples(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri, tmp_named_graph_uri, implicit_to_facts_ttl_file)

    # Vider le répertoire (en sauvant le graphe nommé des faits dans un fichier TTL) et le recharger
    gd.export_named_graph_and_reload_repository(graphdb_url, repository_name, facts_ttl_file, facts_named_graph_name, ont_file, ontology_named_graph_name)

    
def add_missing_elements_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri):
    """
    Ajouter des éléments comme les changements, les événements, les attributs et leurs versions
    """

    query = f"""
    PREFIX prov: <http://www.w3.org/ns/prov#>
    PREFIX geo: <http://www.opengis.net/ont/geosparql#>
    PREFIX geofla: <http://data.ign.fr/def/geofla#>
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX factoids: <http://rdf.geohistoricaldata.org/id/address/factoids/>
    PREFIX ctype: <http://rdf.geohistoricaldata.org/id/codes/address/changeType/>
    PREFIX atype: <http://rdf.geohistoricaldata.org/id/codes/address/attributeType/>
    DELETE {{
        GRAPH ?g {{ 
            ?landmark geo:asWKT ?geom ; geofla:numInsee ?inseeCode.
        }}
    }}
    INSERT {{
        GRAPH ?g {{
            ?landmark addr:hasAttribute ?nameAttribute, ?geomAttribute, ?inseeCodeAttribute ; prov:wasDerivedFrom ?provenance.
            ?nameAttribute a addr:Attribute ; addr:isAttributeType atype:Name ; addr:hasAttributeVersion ?versionNameAttribute.
            ?inseeCodeAttribute a addr:Attribute ; addr:isAttributeType atype:InseeCode ; addr:hasAttributeVersion ?versionInseeCodeAttribute.
            ?geomAttribute a addr:Attribute ; addr:isAttributeType atype:Geometry ; addr:hasAttributeVersion ?versionGeomAttribute.
            ?versionNameAttribute a addr:AttributeVersion ; addr:versionValue ?label ; prov:wasDerivedFrom ?provenance.
            ?versionInseeCodeAttribute a addr:AttributeVersion ; addr:versionValue ?inseeCode ; prov:wasDerivedFrom ?provenance.
            ?versionGeomAttribute a addr:AttributeVersion ; addr:versionValue ?geom ; prov:wasDerivedFrom ?provenance.
            ?landmarkChangeApp a addr:LandmarkChange ; addr:isChangeType ctype:LandmarkAppearance ;
                addr:appliedTo ?landmark ; addr:dependsOn ?landmarkEventApp ; prov:wasDerivedFrom ?provenance.
            ?landmarkChangeDis a addr:LandmarkChange ; addr:isChangeType ctype:LandmarkDisappearance ;
                addr:appliedTo ?landmark ; addr:dependsOn ?landmarkEventDis ; prov:wasDerivedFrom ?provenance.
            ?versNameAttributeChangeApp a addr:AttributeChange ; addr:isChangeType ctype:AttributeVersionAppearance ;
                addr:appliedTo ?nameAttribute ; addr:dependsOn ?landmarkEventApp ; addr:makesEffective ?versionNameAttribute ; prov:wasDerivedFrom ?provenance.
            ?versNameAttributeChangeDis a addr:AttributeChange ; addr:isChangeType ctype:AttributeVersionDisappearance ;
                addr:appliedTo ?nameAttribute ; addr:dependsOn ?landmarkEventDis ; addr:outdates ?versionNameAttribute ; prov:wasDerivedFrom ?provenance.
            ?inseeCodeAttributeChangeApp a addr:AttributeChange ; addr:isChangeType ctype:AttributeVersionAppearance ;
                addr:appliedTo ?inseeCodeAttribute ; addr:dependsOn ?inseeCodeAttributeEventApp ; addr:makesEffective ?versionInseeCodeAttribute ; prov:wasDerivedFrom ?provenance.
            ?inseeCodeAttributeChangeDis a addr:AttributeChange ; addr:isChangeType ctype:AttributeVersionDisappearance ;
                addr:appliedTo ?inseeCodeAttribute ; addr:dependsOn ?inseeCodeAttributeEventDis ; addr:outdates ?versionInseeCodeAttribute ; prov:wasDerivedFrom ?provenance.
            ?geomAttributeChangeApp a addr:AttributeChange ; addr:isChangeType ctype:AttributeVersionAppearance ;
                addr:appliedTo ?geomAttribute ; addr:dependsOn ?geomAttributeEventApp ; addr:makesEffective ?versionGeomAttribute ; prov:wasDerivedFrom ?provenance.
            ?geomAttributeChangeDis a addr:AttributeChange ; addr:isChangeType ctype:AttributeVersionDisappearance ;
                addr:appliedTo ?geomAttribute ; addr:dependsOn ?geomAttributeEventDis ; addr:outdates ?versionGeomAttribute ; prov:wasDerivedFrom ?provenance.
            ?landmarkEventApp a addr:Event ; prov:wasDerivedFrom ?provenance.
            ?landmarkEventDis a addr:Event ; prov:wasDerivedFrom ?provenance.
            ?inseeCodeAttributeEventApp a addr:Event ; prov:wasDerivedFrom ?provenance.
            ?inseeCodeAttributeEventDis a addr:Event ; prov:wasDerivedFrom ?provenance.
            ?geomAttributeEventApp a addr:Event ; prov:wasDerivedFrom ?provenance.
            ?geomAttributeEventDis a addr:Event ; prov:wasDerivedFrom ?provenance.
        }}  
    }}
    WHERE {{
        {{
            SELECT * {{
                BIND({factoids_named_graph_uri.n3()} AS ?g)
                GRAPH ?g {{
                    ?landmark a addr:Landmark ; rdfs:label ?label.
                    OPTIONAL {{?landmark geo:asWKT ?geom}}
                    OPTIONAL {{?landmark geofla:numInsee ?inseeCode}}
                    OPTIONAL {{?landmark prov:wasDerivedFrom ?provenance.}}
                }}
            }}
        }}
        BIND(URI(CONCAT(STR(URI(factoids:)), "CGA_", STRUUID())) AS ?landmarkChangeApp)
        BIND(URI(CONCAT(STR(URI(factoids:)), "CGD_", STRUUID())) AS ?landmarkChangeDis)
        BIND(URI(CONCAT(STR(URI(factoids:)), "EVA_", STRUUID())) AS ?landmarkEventApp)
        BIND(URI(CONCAT(STR(URI(factoids:)), "EVD_", STRUUID())) AS ?landmarkEventDis)
        BIND(URI(CONCAT(STR(URI(factoids:)), "AN_", STRUUID())) AS ?nameAttribute)
        BIND(URI(CONCAT(STR(URI(factoids:)), "ANV_", STRUUID())) AS ?versionNameAttribute)
        BIND(URI(CONCAT(STR(URI(factoids:)), "CGA_AN_", STRUUID())) AS ?versNameAttributeChangeApp)
        BIND(URI(CONCAT(STR(URI(factoids:)), "CGD_AN_", STRUUID())) AS ?versNameAttributeChangeDis)
        BIND(IF(BOUND(?inseeCode), URI(CONCAT(STR(URI(factoids:)), "AI_", STRUUID())), ?x) AS ?inseeCodeAttribute)
        BIND(IF(BOUND(?inseeCode), URI(CONCAT(STR(URI(factoids:)), "AIV_", STRUUID())), ?x) AS ?versionInseeCodeAttribute)
        BIND(IF(BOUND(?inseeCode), URI(CONCAT(STR(URI(factoids:)), "CGA_AI_", STRUUID())), ?x) AS ?inseeCodeAttributeChangeApp)
        BIND(IF(BOUND(?inseeCode), URI(CONCAT(STR(URI(factoids:)), "CGD_AI_", STRUUID())), ?x) AS ?inseeCodeAttributeChangeDis)
        BIND(IF(BOUND(?inseeCode), URI(CONCAT(STR(URI(factoids:)), "EVA_AI_", STRUUID())), ?x) AS ?inseeCodeAttributeEventApp)
        BIND(IF(BOUND(?inseeCode), URI(CONCAT(STR(URI(factoids:)), "EVD_AI_", STRUUID())), ?x) AS ?inseeCodeAttributeEventDis)
        BIND(IF(BOUND(?geom), URI(CONCAT(STR(URI(factoids:)), "AG_", STRUUID())), ?x) AS ?geomAttribute)
        BIND(IF(BOUND(?geom), URI(CONCAT(STR(URI(factoids:)), "AGV_", STRUUID())), ?x) AS ?versionGeomAttribute)
        BIND(IF(BOUND(?geom), URI(CONCAT(STR(URI(factoids:)), "CGA_AG_", STRUUID())), ?x) AS ?geomAttributeChangeApp)
        BIND(IF(BOUND(?geom), URI(CONCAT(STR(URI(factoids:)), "CGD_AG_", STRUUID())), ?x) AS ?geomAttributeChangeDis)
        BIND(IF(BOUND(?geom), URI(CONCAT(STR(URI(factoids:)), "EVA_AG_", STRUUID())), ?x) AS ?geomAttributeEventApp)
        BIND(IF(BOUND(?geom), URI(CONCAT(STR(URI(factoids:)), "EVD_AG_", STRUUID())), ?x) AS ?geomAttributeEventDis)
    }}
    """
    
    gd.update_query(query, graphdb_url, repository_name)

def create_same_as_links_from_queries(graphdb_url, repository_name):
    """
    Create some `owl:sameAs` links according rules thanks to queries
    """

    prefixes = """
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX facts: <http://rdf.geohistoricaldata.org/id/address/facts/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    """

    query1 = prefixes + """
    INSERT {
        ?attr1 owl:sameAs ?attr2.   
    }
    WHERE {
        ?attr1 a addr:Attribute ; addr:isAttributeType ?attrType.
        ?attr2 a addr:Attribute ; addr:isAttributeType ?attrType.
        ?lm addr:hasAttribute ?attr1, ?attr2.
        FILTER (?attr1 != ?attr2)
    }
    """

    query2 = prefixes + """
    INSERT {
        ?cg1 owl:sameAs ?cg2.   
    }
    WHERE {
        ?cg1 a addr:Change ; addr:isChangeType ?cgType ; addr:dependsOn ?ev ; addr:appliedTo ?elem.
        ?cg2 a addr:Change ; addr:isChangeType ?cgType ; addr:dependsOn ?ev ; addr:appliedTo ?elem.
        FILTER (?cg1 != ?cg2)
    }
    """

    query3 = prefixes + """
    INSERT {
        ?cg1 owl:sameAs ?cg2.   
    }
    WHERE {
        ?cg1 a addr:LandmarkChange ; addr:isChangeType ?cgType ; addr:appliedTo ?elem.
        ?cg2 a addr:LandmarkChange ; addr:isChangeType ?cgType ; addr:appliedTo ?elem.
        FILTER (?cg1 != ?cg2)
    }
    """

    query4 = prefixes + """
    INSERT {
        ?cg1 owl:sameAs ?cg2.   
    }
    WHERE {
        ?cg1 a addr:LandmarkRelationChange ; addr:isChangeType ?cgType ; addr:appliedTo ?elem.
        ?cg2 a addr:LandmarkRelationChange ; addr:isChangeType ?cgType ; addr:appliedTo ?elem.
        FILTER (?cg1 != ?cg2)
    }
    """

    query5 = prefixes + """
    INSERT {
        ?cg1 owl:sameAs ?cg2.   
    }
    WHERE {
        ?cg1 a addr:AttributeChange ; addr:appliedTo ?elem ; addr:makesEffective ?attrVersion.
        ?cg2 a addr:AttributeChange ; addr:appliedTo ?elem ; addr:makesEffective ?attrVersion.
        FILTER (?cg1 != ?cg2)
    }
    """

    query6 = prefixes + """
    INSERT {
        ?cg1 owl:sameAs ?cg2.   
    }
    WHERE {
        ?cg1 a addr:AttributeChange ; addr:appliedTo ?elem ; addr:outdates ?attrVersion.
        ?cg2 a addr:AttributeChange ; addr:appliedTo ?elem ; addr:outdates ?attrVersion.
        FILTER (?cg1 != ?cg2)
    }
    """

    query7 = prefixes + """
    INSERT {
        ?ev1 owl:sameAs ?ev2.   
    }
    WHERE {
        ?ev1 a addr:Event.
        ?ev2 a addr:Event.
        ?cg addr:dependsOn ?ev1, ?ev2.
        FILTER (?ev1 != ?ev2)
    }
    """

    query8 = prefixes + """
    INSERT {
        ?ti1 owl:sameAs ?ti2.   
    }
    WHERE {
        ?ti1 a addr:CrispTimeInstant ; addr:timeStamp ?timeStamp ; addr:timePrecision ?timePrec ; addr:timeCalendar ?timeCal.
        ?ti2 a addr:CrispTimeInstant ; addr:timeStamp ?timeStamp ; addr:timePrecision ?timePrec ; addr:timeCalendar ?timeCal.
        FILTER (?ti1 != ?ti2)
    }
    """
    queries = [query1, query2, query3, query4, query5, query6, query7, query8]
    for query in queries:
        gd.update_query(query, graphdb_url, repository_name)
