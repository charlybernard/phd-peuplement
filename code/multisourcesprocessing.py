import os
import datetime
from rdflib import Graph, Namespace, Literal, BNode, URIRef, XSD, SKOS
from rdflib.namespace import RDF
import strprocessing as sp
import timeprocessing as tp
import ontorefine as otr
import graphdb as gd
import graphrdf as gr
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

def add_alt_and_hidden_labels_to_landmarks(graphdb_url, repository_name, named_graph_uri:URIRef):
    add_alt_and_hidden_labels_for_name_attribute_versions(graphdb_url, repository_name, named_graph_uri)
    add_alt_and_hidden_labels_to_landmarks_from_name_attribute_versions(graphdb_url, repository_name, named_graph_uri)

def add_alt_and_hidden_labels_for_name_attribute_versions(graphdb_url, repository_name, factoids_named_graph_uri:URIRef):
    prefixes = """
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX atype: <http://rdf.geohistoricaldata.org/id/codes/address/attributeType/>
    PREFIX ltype: <http://rdf.geohistoricaldata.org/id/codes/address/landmarkType/>
    """

    query = prefixes + f"""
        SELECT ?av ?name ?nameType WHERE {{
            ?av a addr:AttributeVersion ; addr:versionValue ?name ; addr:isAttributeVersionOf [a addr:Attribute ; addr:isAttributeType atype:Name ; addr:isAttributeOf [a addr:Landmark ; addr:isLandmarkType ?ltype]] .
            BIND(IF(?ltype IN (ltype:HouseNumber, ltype:StreetNumber, ltype:DistrictNumber), "housenumber", 
                IF(?ltype = ltype:Thoroughfare, "thoroughfare", 
                    IF(?ltype IN (ltype:City, ltype:District, ltype:PostalCodeArea), "area", ""))) AS ?nameType)
        
        }}
        """

    results = gd.select_query_to_json(query, graphdb_url, repository_name)

    query_lines = ""
    for elem in results.get("results").get("bindings"):
        # Récupération des URIs (attibut et version d'attribut) et de la géométrie
        rel_av = gr.convert_result_elem_to_rdflib_elem(elem.get('av'))
        rel_name = gr.convert_result_elem_to_rdflib_elem(elem.get('name'))
        rel_name_type = gr.convert_result_elem_to_rdflib_elem(elem.get('nameType'))
        normalized_name, simplified_name = sp.normalize_and_simplify_name_version(rel_name.strip(), rel_name_type.strip(), rel_name.language)
        rel_name_lang = rel_name.language

        normalized_name_lit = Literal(normalized_name, lang=rel_name_lang)
        simplified_name_lit = Literal(simplified_name, lang=rel_name_lang)
        query_lines += f"{rel_av.n3()} {SKOS.altLabel.n3()} {normalized_name_lit.n3()} ; {SKOS.hiddenLabel.n3()} {simplified_name_lit.n3()}.\n"
        
    query = prefixes + f"""
        INSERT DATA {{
            GRAPH {factoids_named_graph_uri.n3()} {{
                {query_lines}
            }}
        }}
        """

    gd.update_query(query, graphdb_url, repository_name)

def add_alt_and_hidden_labels_to_landmarks_from_name_attribute_versions(graphdb_url, repository_name, named_graph_uri:URIRef):
    prefixes = """
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX atype: <http://rdf.geohistoricaldata.org/id/codes/address/attributeType/>
    PREFIX ltype: <http://rdf.geohistoricaldata.org/id/codes/address/landmarkType/>
    """

    query = prefixes + f"""
        INSERT {{
            GRAPH ?g {{ ?lm skos:altLabel ?altLabel ; skos:hiddenLabel ?hiddenLabel . }}
        }}
        WHERE {{
            BIND({named_graph_uri.n3()} AS ?g)
            GRAPH ?g {{ ?lm a addr:Landmark }}
            ?lm addr:hasAttribute [a addr:Attribute; addr:isAttributeType atype:Name ; addr:hasAttributeVersion ?av ] .
            OPTIONAL {{ ?av skos:altLabel ?altLabel . }}
            OPTIONAL {{ ?av skos:hiddenLabel ?hiddenLabel . }}
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)


def create_time_resources_for_current_sources(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, time_description:dict={}):
    """
    Ajout de ressources temporelles pour des sources décrivant des données actuelles
    """

    time_description = tp.get_valid_time_description(time_description)
    create_time_resources(graphdb_url, repository_name, factoids_named_graph_uri, time_description)

def create_time_resources(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, time_description:dict):
    """
    À partir de la variable `geojson_time` qui décrit un intervalle temporel de validité des données de la source, ajouter des instants temporels flous à tous les événements :
    - pour les événements liés à des changements d'apparition, on considère qu'ils sont liés à un instant qui indique la date au plus tard connue (hasTimeBefore)
    - pour les événements liés à des changements de disparition, on considère qu'ils sont liés à un instant qui indique la date au plus tôt connue (hasTimeAfter)

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

    start_time = tp.get_time_instant_elements(time_description.get("start_time"))
    end_time = tp.get_time_instant_elements(time_description.get("end_time"))

    add_time_instants_for_timeless_events(graphdb_url, repository_name, factoids_named_graph_uri, "start", start_time[0], start_time[1], start_time[2])
    add_time_instants_for_timeless_events(graphdb_url, repository_name, factoids_named_graph_uri, "end", end_time[0], end_time[1], end_time[2])


def add_time_instants_for_timeless_events(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, time_type:str, stamp:Literal, precision:URIRef, calendar:URIRef):
    if None in [stamp, precision, calendar]:
        return None
    
    if time_type == "start":
        time_predicate = ":hasTimeBefore"
        change_types = ["ctype:AttributeVersionAppearance", "ctype:LandmarkAppearance", "ctype:LandmarkRelationAppearance"]
    elif time_type == "end":
        time_predicate = ":hasTimeAfter"
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

def create_unlinked_resources(graphdb_url, repository_name, query_prefixes, refactoids_class:URIRef, refactoids_prefix:str, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
    """
    Create resources as facts and create a provenance link for each one
    """

    query = query_prefixes + f"""
        INSERT {{
            GRAPH {facts_named_graph_uri.n3()} {{
                ?resource a ?type.
            }}
            GRAPH {factoids_named_graph_uri.n3()} {{
                ?resource addr:isSimilarTo ?sourceResource.
            }}
        }}
        WHERE {{
            ?type rdfs:subClassOf* {refactoids_class.n3()}.
            GRAPH {factoids_named_graph_uri.n3()} {{
                ?sourceResource a ?type.
            }}
            MINUS {{
                ?fact a {refactoids_class.n3()} ; addr:isSimilarTo ?sourceResource. 
                FILTER(?fact != ?sourceResource)
            }}
            BIND(URI(CONCAT(STR(URI(facts:)), "{refactoids_prefix}_", STRUUID())) AS ?resource)
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def create_similar_links_between_landmarks(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
    """
    Create `addr:isSimilarTo` links between similar landmarks.
    """

    create_similar_links_between_areas(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)
    create_similar_links_between_thoroughfares(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)
    create_similar_links_between_housenumbers(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)

def create_similar_links_between_areas(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
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
            ?factsLandmark addr:isSimilarTo ?sourceLandmark.
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
        MINUS {{?factsLandmark addr:isSimilarTo ?sourceLandmark}}
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def create_similar_links_between_thoroughfares(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
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
            ?factsLandmark addr:isSimilarTo ?sourceLandmark.
        }}
    }}
    WHERE {{
        GRAPH {factoids_named_graph_uri.n3()} {{
            ?sourceLandmark a addr:Landmark ; addr:isLandmarkType ltype:Thoroughfare.
        }}
        GRAPH {facts_named_graph_uri.n3()} {{
            ?factsLandmark a addr:Landmark ; addr:isLandmarkType ltype:Thoroughfare.
           }}
        MINUS {{?factsLandmark addr:isSimilarTo ?sourceLandmark}}
        ?sourceLandmark skos:hiddenLabel ?label.
        ?factsLandmark skos:hiddenLabel ?label.
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)


def create_similar_links_between_housenumbers(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
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
            ?factsHN addr:isSimilarTo ?sourceHN.
        }}
    }}
    WHERE {{
        BIND(ltype:HouseNumber AS ?landmarkType)
        BIND(lrtype:Along AS ?landmarkRelationType)
        GRAPH {factoids_named_graph_uri.n3()} {{ ?sourceHN a addr:Landmark }} 
        GRAPH {facts_named_graph_uri.n3()} {{ ?factsHN a addr:Landmark }}
        ?sourceLR a addr:LandmarkRelation ; addr:isLandmarkRelationType ?landmarkRelationType ; addr:locatum ?sourceHN ; addr:relatum ?sourceTH.
        ?factsLR a addr:LandmarkRelation ; addr:isLandmarkRelationType ?landmarkRelationType ; addr:locatum ?factsHN ; addr:relatum ?factsTH.
        ?factsTH addr:isSimilarTo ?sourceTH .
        ?sourceHN addr:isLandmarkType ?landmarkType ; skos:hiddenLabel ?label.
        ?factsHN addr:isLandmarkType ?landmarkType ; skos:hiddenLabel ?label.
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def create_similar_links_between_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
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
        GRAPH {factoids_named_graph_uri.n3()} {{ 
            ?lr1 addr:isSimilarTo ?lr2 .
        }}
    }}
    WHERE {{
        BIND({facts_named_graph_uri.n3()} AS ?gf)
        BIND({factoids_named_graph_uri.n3()} AS ?gs)
        GRAPH ?gf {{ ?lr1 a ?typeLR1 . }}
        GRAPH ?gs {{ ?lr2 a ?typeLR2 . }}
        ?typeLR1 rdfs:subClassOf addr:LandmarkRelation .
        ?typeLR2 rdfs:subClassOf addr:LandmarkRelation .
        ?lr1 addr:isLandmarkRelationType ?lrt ; addr:locatum ?l1 .
        ?lr2 addr:isLandmarkRelationType ?lrt ; addr:locatum ?l2 .
        ?l1 addr:isSimilarTo ?l2 .
        MINUS {{
            SELECT DISTINCT ?lr1 ?lr2 WHERE {{
                ?lr1 addr:isLandmarkRelationType ?lrt ; addr:locatum ?l1 .
                ?lr2 addr:isLandmarkRelationType ?lrt ; addr:locatum ?l2 .
                ?l1 addr:isSimilarTo ?l2 .
                ?lr1 addr:relatum ?r1 .
                MINUS {{
                    ?lr2 addr:relatum ?r2 .
                    ?r1 addr:isSimilarTo ?r2 .
                }}
            }}
        }}
        MINUS
        {{
            SELECT DISTINCT ?lr1 ?lr2 WHERE {{
                ?lr1 addr:isLandmarkRelationType ?lrt ; addr:locatum ?l1 .
                ?lr2 addr:isLandmarkRelationType ?lrt ; addr:locatum ?l2 .
                ?l1 addr:isSimilarTo ?l2 .
                ?lr2 addr:relatum ?r2.
                MINUS {{
                    ?lr1 addr:relatum ?r1 .
                    ?r1 addr:isSimilarTo ?r2 .
                }}
            }}
        }}  
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def transfer_implicit_triples(graphdb_url, repository_name, namespace_prefixes, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
    query_prefixes = gd.get_query_prefixes_from_namespaces(namespace_prefixes)

    query = query_prefixes + f"""
        INSERT {{
            GRAPH ?gf {{ ?elemFact ?p ?o }}
        }} WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?gs) 
            BIND({facts_named_graph_uri.n3()} AS ?gf)
            ?elemFact addr:isSimilarTo ?elemSource .
            {{
                GRAPH ?gs {{ ?elemSource ?p ?oSource }}
                ?oFact addr:isSimilarTo ?oSource .
                GRAPH ?gs {{ ?oSource a ?oSourceType }}
                GRAPH ?gf {{ ?oFact a ?oFactType }}
                BIND(?oFact AS ?o)
            }} UNION {{
                GRAPH ?gs {{ ?elemSource ?p ?oSource }}
                MINUS {{ GRAPH ?gs {{ ?oSource a ?oSourceType }} }}
                BIND(?oSource AS ?o)
            }}
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)


# def transfer_implicit_triples(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
#     """
#     Transfert implicit triples to named graph whose uri is `facts_named_graph_uri` which are deduced from addr:isSimilarTo links from ressources between `factoids_named_graph_uri` and `facts_named_graph_uri`
#     """

#     interesting_properties = ["addr:isAttributeType","addr:isChangeType","addr:isLandmarkType","addr:isLandmarkRelationType",
#                               "addr:hasTime","addr:hasEarliestTimeInstant","addr:hasLatestTimeInstant","addr:hasTimeAfter","addr:hasTimeBefore",
#                               "addr:timeCalendar","addr:timePrecision","addr:timeStamp",
#                               "addr:hasAttribute","addr:hasAttributeVersion","addr:versionValue",
#                               "addr:appliedTo","addr:dependsOn","addr:makesEffective","addr:outdates","addr:targets",
#                               "addr:locatum","addr:relatum","addr:firstStep","addr:nextStep",
#                               "rdfs:label","skos:hiddenLabel","skos:closeMatch","rico:isOrWasDescribedBy","prov:wasDerivedFrom"
#                               ]
    
#     interesting_properties_str_list = ",".join(interesting_properties)

#     query = f"""
#         PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
#         PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
#         PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>
#         PREFIX prov: <http://www.w3.org/ns/prov#>
#         PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>

#         INSERT {{
#             GRAPH ?g {{ ?s ?p ?o }} 
#         }} WHERE {{
#             BIND({facts_named_graph_uri.n3()} AS ?g)
#             BIND({factoids_named_graph_uri.n3()} AS ?gs)
#             ?s ?p ?o.
#             GRAPH ?g {{?s a ?sType}}

#             MINUS {{
#                 GRAPH ?g {{ ?s ?p ?o. }}
#             }}
#             MINUS {{
#                 GRAPH ?gs {{ ?o a ?oType. }}
#             }}
#             FILTER(?p in ({interesting_properties_str_list}))
#         }}
#     """

#     gd.update_query(query, graphdb_url, repository_name)


def link_factoids_with_facts(graphdb_url, repository_name, namespace_prefixes:dict, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
    """
    Landmarks are created as follows:
        * creation of links (using `addr:isSimilarTo`) between landmarks in the facts named graph and those which are in the factoid named graph ;
        * using inference rules, new `addr:isSimilarTo` links are deduced
        * for each resource defined in the factoids, we check whether it exists in the fact graph (if it is linked with a `addr:isSimilarTo` to a resource in the fact graph)
        * for unlinked factoid resources, we create its equivalent in the fact graph
    """

    addr_ns = namespace_prefixes["addr"]
    query_prefixes = gd.get_query_prefixes_from_namespaces(namespace_prefixes)

    # resource_classes = {"LM": addr_ns["Landmark"], "LR": addr_ns["LandmarkRelation"], "ADDR": addr_ns["Address"],
    #                     "ATTR": addr_ns["Attribute"], "AV":addr_ns["AttributeVersion"], "CG": addr_ns["Change"], "EV":addr_ns["Event"], "TE": addr_ns["TemporalEntity"]}

    # for prefix, class_name in resource_classes.items():
    #     create_unlinked_resources(graphdb_url, repository_name, class_name, prefix, factoids_named_graph_uri, facts_named_graph_uri)

    create_similar_links_between_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)
    create_unlinked_resources(graphdb_url, repository_name, query_prefixes, addr_ns["Landmark"], "LM", factoids_named_graph_uri, facts_named_graph_uri)

    create_similar_links_between_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)
    create_unlinked_resources(graphdb_url, repository_name, query_prefixes, addr_ns["LandmarkRelation"], "LR", factoids_named_graph_uri, facts_named_graph_uri)

    create_unlinked_resources(graphdb_url, repository_name, query_prefixes, addr_ns["Address"], "ADDR", factoids_named_graph_uri, facts_named_graph_uri)

    create_similar_links_for_attributes(graphdb_url, repository_name, query_prefixes, factoids_named_graph_uri, facts_named_graph_uri)
    create_unlinked_resources(graphdb_url, repository_name, query_prefixes, addr_ns["Attribute"], "AT", factoids_named_graph_uri, facts_named_graph_uri)
    create_unlinked_resources(graphdb_url, repository_name, query_prefixes, addr_ns["AttributeVersion"], "AV", factoids_named_graph_uri, facts_named_graph_uri)

    create_similar_links_for_changes(graphdb_url, repository_name, query_prefixes, factoids_named_graph_uri, facts_named_graph_uri)
    create_unlinked_resources(graphdb_url, repository_name, query_prefixes, addr_ns["Change"], "CG", factoids_named_graph_uri, facts_named_graph_uri)

    create_similar_links_for_events(graphdb_url, repository_name, query_prefixes, factoids_named_graph_uri, facts_named_graph_uri)
    create_unlinked_resources(graphdb_url, repository_name, query_prefixes, addr_ns["Event"], "EV", factoids_named_graph_uri, facts_named_graph_uri)

    create_similar_links_for_temporal_entities(graphdb_url, repository_name, query_prefixes, factoids_named_graph_uri, facts_named_graph_uri)
    create_unlinked_resources(graphdb_url, repository_name, query_prefixes, addr_ns["TemporalEntity"], "TE", factoids_named_graph_uri, facts_named_graph_uri)

def import_factoids_in_facts(graphdb_url, repository_name, namespace_prefixes, factoids_named_graph_name, facts_named_graph_name):
    facts_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, facts_named_graph_name))
    factoids_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, factoids_named_graph_name))
    
    # Ajout de labels normalisés et simplifiés pour les repères (du graphe des factoïdes) afin de faire des liens avec les repères des faits
    add_alt_and_hidden_labels_to_landmarks(graphdb_url, repository_name, factoids_named_graph_uri)
    
    link_factoids_with_facts(graphdb_url, repository_name, namespace_prefixes, factoids_named_graph_uri, facts_named_graph_uri)
    
    # Transférer les triplets implicites intéressants dans le graphe nommé des faits
    transfer_implicit_triples(graphdb_url, repository_name, namespace_prefixes, factoids_named_graph_uri, facts_named_graph_uri)

    # Supprimer le graphe nommé des factoïdes
    gd.remove_named_graph(graphdb_url, repository_name, factoids_named_graph_name)

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

def add_missing_elements_for_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri):
    """
    Ajouter des éléments aux relations entre repères comme les changements, les événements, les attributs et leurs versions
    """

    query = f"""
    PREFIX ctype: <http://rdf.geohistoricaldata.org/id/codes/address/changeType/>
    PREFIX lrtype: <http://rdf.geohistoricaldata.org/id/codes/address/landmarkRelationType/>
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX factoids: <http://rdf.geohistoricaldata.org/id/address/factoids/>

    INSERT {{
        GRAPH ?g {{
            ?lrChangeApp a addr:LandmarkRelationChange ; addr:isChangeType ?cgType ; addr:appliedTo ?lr ; addr:dependsOn ?lrEventApp .
            ?lrEventApp a addr:Event .
        }}
    }}
    WHERE {{
        BIND({factoids_named_graph_uri.n3()} AS ?g)
        {{
            SELECT * WHERE {{
                ?lr a addr:LandmarkRelation.
                {{
                    BIND(ctype:LandmarkRelationAppearance AS ?cgType)
                }} UNION {{
                    BIND(ctype:LandmarkRelationDisappearance AS ?cgType)
                }}
                MINUS {{ ?cg a addr:Change ; addr:appliedTo ?lr ; addr:isChangeType ?cgType }}
            }}
        }}
        
        BIND(URI(CONCAT(STR(URI(factoids:)), "CG_LR_", STRUUID())) AS ?lrChangeApp)
        BIND(URI(CONCAT(STR(URI(factoids:)), "EV_LR_", STRUUID())) AS ?lrEventApp)
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)


def create_similar_links_for_attributes(graphdb_url, repository_name, query_prefixes, factoids_named_graph_uri, facts_named_graph_uri):
    query = query_prefixes + f"""
        INSERT {{
            GRAPH ?gs {{
                ?attr1 addr:isSimilarTo ?attr2.
            }}   
        }}
        WHERE {{
            BIND({facts_named_graph_uri.n3()} AS ?gf)
            BIND({factoids_named_graph_uri.n3()} AS ?gs)
            GRAPH ?gf {{ ?attr1 a addr:Attribute . }}
            GRAPH ?gs {{ ?attr2 a addr:Attribute . }}
            ?attr1 addr:isAttributeOf ?lm1 ; addr:isAttributeType ?attrType .
            ?attr2 addr:isAttributeOf ?lm2 ; addr:isAttributeType ?attrType .
            ?lm1 addr:isSimilarTo ?lm2 .
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def create_similar_links_for_changes(graphdb_url, repository_name, query_prefixes, factoids_named_graph_uri, facts_named_graph_uri):
    
    # Create links for similar changes (excepted for attribute changes) : two changes are similar if they are applied to the same element are their type is the same
    query1 = query_prefixes + f"""
        INSERT {{
            GRAPH ?gs {{
                ?cg1 addr:isSimilarTo ?cg2.
            }}   
        }}
        WHERE {{
            BIND({facts_named_graph_uri.n3()} AS ?gf)
            BIND({factoids_named_graph_uri.n3()} AS ?gs)
            ?changeClass rdfs:subClassOf addr:Change .
            MINUS {{ ?changeClass rdfs:subClassOf addr:AttributeChange }}
            GRAPH ?gf {{ ?cg1 a ?changeClass . }}
            GRAPH ?gs {{ ?cg2 a ?changeClass . }}
            ?cg1 addr:appliedTo ?elem1 ; addr:isChangeType ?cgType .
            ?cg2 addr:appliedTo ?elem2 ; addr:isChangeType ?cgType .
            ?elem1 addr:isSimilarTo ?elem2 .
        }}
    """

    # Create links for similar attribute changes
    query2 = query_prefixes + f"""
        INSERT {{
            GRAPH ?gs {{
                ?cg1 addr:isSimilarTo ?cg2.
            }}   
        }}
        WHERE {{
            BIND({facts_named_graph_uri.n3()} AS ?gf)
            BIND({factoids_named_graph_uri.n3()} AS ?gs)
            ?changeClass rdfs:subClassOf addr:AttributeChange .
            GRAPH ?gf {{
                ?cg1 a ?changeClass .
                ?av1 a addr:AttributeVersion .
                }}
            GRAPH ?gs {{
                ?cg2 a ?changeClass .
                ?av2 a addr:AttributeVersion .
                }}
            ?cg1 ?p ?av1 .
            ?cg2 ?p ?av2 .
            FILTER (?p IN (addr:makesEffective, addr:outdates))
            ?av1 addr:isSimilarTo ?av2 .
        }}
    """

    queries = [query1, query2]
    for query in queries:
        gd.update_query(query, graphdb_url, repository_name)


def create_similar_links_for_events(graphdb_url, repository_name, query_prefixes, factoids_named_graph_uri, facts_named_graph_uri):
    
    # Create links for similar events
    query = query_prefixes + f"""
        INSERT {{
            GRAPH ?gs {{
                ?ev1 addr:isSimilarTo ?ev2.
            }}   
        }}
        WHERE {{
            BIND({facts_named_graph_uri.n3()} AS ?gf)
            BIND({factoids_named_graph_uri.n3()} AS ?gs)
            GRAPH ?gf {{ ?ev1 a addr:Event . }}
            GRAPH ?gs {{ ?ev2 a addr:Event . }}
            ?cg1 addr:dependsOn ?ev1 .
            ?cg2 addr:dependsOn ?ev2 .
            ?cg1 addr:isSimilarTo ?cg2 .
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def create_similar_links_for_temporal_entities(graphdb_url, repository_name, query_prefixes, factoids_named_graph_uri, facts_named_graph_uri):
    
    # Create links for similar crisp time instants
    query = query_prefixes + f"""
        INSERT {{
            GRAPH ?gs {{
                ?t1 addr:isSimilarTo ?t2.
            }}   
        }}
        WHERE {{
            BIND({facts_named_graph_uri.n3()} AS ?gf)
            BIND({factoids_named_graph_uri.n3()} AS ?gs)
            GRAPH ?gf {{
                ?ev1 a addr:Event ; ?p ?t1 .
                ?t1 a addr:CrispTimeInstant .
                }}
            GRAPH ?gs {{
                ?ev2 a addr:Event ; ?p ?t2 .
                ?t2 a addr:CrispTimeInstant .
                }}
            FILTER (?p IN (addr:hasTime, addr:hasTimeBefore, addr:hasTimeAfter))
            ?t1 addr:timeStamp ?timeStamp ; addr:timeCalendar ?timeCal ; addr:timePrecision ?timePrec .
            ?t2 addr:timeStamp ?timeStamp ; addr:timeCalendar ?timeCal ; addr:timePrecision ?timePrec .
            ?ev1 addr:isSimilarTo ?ev2 .
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)