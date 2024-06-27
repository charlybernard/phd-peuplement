import os
import datetime
from rdflib import Graph, Namespace, Literal, BNode, URIRef, XSD, SKOS
from rdflib.namespace import RDF
from namespaces import NameSpaces
import strprocessing as sp
import geomprocessing as gp
import timeprocessing as tp
import ontorefine as otr
import graphdb as gd
import graphrdf as gr
import curl as curl

np = NameSpaces()

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
    query = np.query_prefixes + f"""
        SELECT ?av ?name ?ltype WHERE {{
            ?av a addr:AttributeVersion ;
                addr:versionValue ?name ;
                addr:isAttributeVersionOf [
                    a addr:Attribute ;
                    addr:isAttributeType atype:Name ;
                    addr:isAttributeOf [a addr:Landmark ; addr:isLandmarkType ?ltype]] .        
        }}
        """

    results = gd.select_query_to_json(query, graphdb_url, repository_name)

    query_lines = ""
    for elem in results.get("results").get("bindings"):
        # Récupération des URIs (attibut et version d'attribut) et de la géométrie
        rel_av = gr.convert_result_elem_to_rdflib_elem(elem.get('av'))
        rel_name = gr.convert_result_elem_to_rdflib_elem(elem.get('name'))
        rel_landmark_type = gr.convert_result_elem_to_rdflib_elem(elem.get('ltype'))

        if rel_landmark_type == np.LTYPE["Thoroughfare"]:
            lm_label_type = "thoroughfare"
        elif rel_landmark_type in [np.LTYPE["City"], np.LTYPE["District"]]:
            lm_label_type = "area"
        elif rel_landmark_type in [np.LTYPE["HouseNumber"],np.LTYPE["StreetNumber"],np.LTYPE["DistrictNumber"],np.LTYPE["PostalCodeArea"]]:
            lm_label_type = "housenumber"
        else:
            lm_label_type = None

        normalized_name, simplified_name = sp.normalize_and_simplify_name_version(rel_name.strip(), lm_label_type, rel_name.language)


        if normalized_name is not None:
            normalized_name_lit = Literal(normalized_name, lang=rel_name.language)
            query_lines += f"{rel_av.n3()} {SKOS.altLabel.n3()} {normalized_name_lit.n3()}.\n"
        if simplified_name is not None:
            simplified_name_lit = Literal(simplified_name, lang=rel_name.language)
            query_lines += f"{rel_av.n3()} {SKOS.hiddenLabel.n3()} {simplified_name_lit.n3()}.\n"
        
    query = np.query_prefixes + f"""
        INSERT DATA {{
            GRAPH {factoids_named_graph_uri.n3()} {{
                {query_lines}
            }}
        }}
        """

    gd.update_query(query, graphdb_url, repository_name)

def add_alt_and_hidden_labels_to_landmarks_from_name_attribute_versions(graphdb_url, repository_name, named_graph_uri:URIRef):
    query = np.query_prefixes + f"""
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

def merge_landmark_multiple_geometries(graphdb_url, repository_name, factoids_named_graph_uri):
    """
    Fusion des géométries d'un landmark si ce dernier en a plus d'une
    """

    # Requête pour sélectionner toutes les géométries des repères
    query = np.query_prefixes + """SELECT * WHERE { ?lm a addr:Landmark ; geo:asWKT ?geom }"""
    results = gd.select_query_to_json(query, graphdb_url, repository_name)

    landmark_geoms = {}

    for elem in results.get("results").get("bindings"):
        # Récupération des URIs (attibut et version d'attribut) et de la géométrie
        rel_lm = gr.convert_result_elem_to_rdflib_elem(elem.get('lm'))
        rel_geom = gr.convert_result_elem_to_rdflib_elem(elem.get('geom'))

        if rel_lm in landmark_geoms.keys():
            landmark_geoms[rel_lm].append(rel_geom)
        else:
            landmark_geoms[rel_lm] = [rel_geom]

    removed_geoms_query_lines, added_geoms_query_lines = "", ""
    for lm, geoms in landmark_geoms.items():
        if len(geoms) > 1:
            wkt_literal = gp.get_union_of_geosparql_wktliterals(geoms)
            added_geoms_query_lines += f"{lm.n3()} geo:asWKT {wkt_literal.n3()}." 
            for geom in geoms:
                removed_geoms_query_lines += f"{lm.n3()} geo:asWKT {geom.n3()}." 

    query = np.query_prefixes + f"""
    INSERT DATA {{
        GRAPH {factoids_named_graph_uri.n3()} {{
            {added_geoms_query_lines}
        }}
    }} ;
    DELETE DATA {{
        {removed_geoms_query_lines}
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
    
    start_time = tp.get_time_instant_elements(time_description.get("start_time"))
    end_time = tp.get_time_instant_elements(time_description.get("end_time"))

    add_time_instants_for_timeless_events(graphdb_url, repository_name, factoids_named_graph_uri, "start", start_time[0], start_time[1], start_time[2])
    add_time_instants_for_timeless_events(graphdb_url, repository_name, factoids_named_graph_uri, "end", end_time[0], end_time[1], end_time[2])


def add_time_instants_for_timeless_events(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, time_type:str, stamp:Literal, precision:URIRef, calendar:URIRef):
    if None in [stamp, precision, calendar]:
        return None
    
    if time_type == "start":
        time_predicate = np.ADDR["hasTimeBefore"]
        change_types = [np.CTYPE["AttributeVersionAppearance"].n3(), np.CTYPE["LandmarkAppearance"].n3(), np.CTYPE["LandmarkRelationAppearance"].n3()]
    elif time_type == "end":
        time_predicate = np.ADDR["hasTimeAfter"]
        change_types = [np.CTYPE["AttributeVersionDisappearance"].n3(), np.CTYPE["LandmarkDisappearance"].n3(), np.CTYPE["LandmarkRelationDisappearance"].n3()]
    else:
        return None
    
    change_types_filter = ", ".join(change_types)

    query = np.query_prefixes + f"""
    INSERT {{
        GRAPH {factoids_named_graph_uri.n3()} {{
            ?ev {time_predicate.n3()} ?timeInstant.
            ?timeInstant a addr:CrispTimeInstant; addr:timeStamp {stamp.n3()} ; addr:timePrecision {precision.n3()} ; addr:timeCalendar {calendar.n3()}.
        }}
    }}
    WHERE {{
        {{
            SELECT DISTINCT ?ev
            WHERE {{
                ?cg a addr:Change; addr:isChangeType ?cgType; addr:dependsOn ?ev.
                MINUS {{ ?ev addr:hasTime ?t }}
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
    query = np.query_prefixes + f"""
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

    prefixes = np.query_prefixes + """
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


    # Ajouter le lien de provenance des versions d'attributs
    query = np.query_prefixes + f"""
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

def create_factoid_repository(graphdb_url, repository_name, tmp_folder, ont_file, ontology_named_graph_name, ruleset_name=None, disable_same_as=False, clear_if_exists=False):
    """
    Initialisation of a repository to create a factoids graph

    `clear_if_exists` is a bool to remove all statements if repository already exists"
    """

    local_config_file_name = f"config_for_{repository_name}.ttl" 
    local_config_file = os.path.join(tmp_folder, local_config_file_name)
    # Repository creation
    gd.create_repository(graphdb_url, repository_name, local_config_file, ruleset_file=None, ruleset_name=ruleset_name, disable_same_as=disable_same_as)
    
    if clear_if_exists:
        gd.clear_repository(graphdb_url, repository_name)

    gd.add_prefixes_to_repository(graphdb_url, repository_name, np.namespaces_with_prefixes)
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
    query = np.query_prefixes + f"""
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

    query = np.query_prefixes + f"""
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

    query = np.query_prefixes + f"""
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

    query = np.query_prefixes + f"""
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

    query = np.query_prefixes + f"""
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

def transfer_implicit_triples(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
    query = np.query_prefixes + f"""
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


def link_factoids_with_facts(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef):
    """
    Landmarks are created as follows:
        * creation of links (using `addr:isSimilarTo`) between landmarks in the facts named graph and those which are in the factoid named graph ;
        * using inference rules, new `addr:isSimilarTo` links are deduced
        * for each resource defined in the factoids, we check whether it exists in the fact graph (if it is linked with a `addr:isSimilarTo` to a resource in the fact graph)
        * for unlinked factoid resources, we create its equivalent in the fact graph
    """

    # resource_classes = {"LM": np.ADDR["Landmark"], "LR": np.ADDR["LandmarkRelation"], "ADDR": np.ADDR["Address"],
    #                     "ATTR": np.ADDR["Attribute"], "AV":np.ADDR["AttributeVersion"], "CG": np.ADDR["Change"], "EV":np.ADDR["Event"], "TE": np.ADDR["TemporalEntity"]}

    # for prefix, class_name in resource_classes.items():
    #     create_unlinked_resources(graphdb_url, repository_name, class_name, prefix, factoids_named_graph_uri, facts_named_graph_uri)

    create_similar_links_between_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)
    create_unlinked_resources(graphdb_url, repository_name, np.ADDR["Landmark"], "LM", factoids_named_graph_uri, facts_named_graph_uri)

    create_similar_links_between_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)
    create_unlinked_resources(graphdb_url, repository_name, np.ADDR["LandmarkRelation"], "LR", factoids_named_graph_uri, facts_named_graph_uri)

    create_unlinked_resources(graphdb_url, repository_name, np.ADDR["Address"], "ADDR", factoids_named_graph_uri, facts_named_graph_uri)

    create_similar_links_for_attributes(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)
    create_unlinked_resources(graphdb_url, repository_name, np.ADDR["Attribute"], "AT", factoids_named_graph_uri, facts_named_graph_uri)
    create_unlinked_resources(graphdb_url, repository_name, np.ADDR["AttributeVersion"], "AV", factoids_named_graph_uri, facts_named_graph_uri)

    create_similar_links_for_changes(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)
    create_unlinked_resources(graphdb_url, repository_name, np.ADDR["Change"], "CG", factoids_named_graph_uri, facts_named_graph_uri)

    create_similar_links_for_events(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)
    create_unlinked_resources(graphdb_url, repository_name, np.ADDR["Event"], "EV", factoids_named_graph_uri, facts_named_graph_uri)

    create_similar_links_for_temporal_entities(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)
    create_unlinked_resources(graphdb_url, repository_name, np.ADDR["TemporalEntity"], "TE", factoids_named_graph_uri, facts_named_graph_uri)

def import_factoids_in_facts(graphdb_url, repository_name, factoids_named_graph_name, facts_named_graph_name):
    facts_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, facts_named_graph_name))
    factoids_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, factoids_named_graph_name))
    
    # Ajout de labels normalisés et simplifiés pour les repères (du graphe des factoïdes) afin de faire des liens avec les repères des faits
    add_alt_and_hidden_labels_to_landmarks(graphdb_url, repository_name, factoids_named_graph_uri)
    
    link_factoids_with_facts(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)
    
    # Transférer les triplets implicites intéressants dans le graphe nommé des faits
    transfer_implicit_triples(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri)

    # Supprimer le graphe nommé des factoïdes
    gd.remove_named_graph(graphdb_url, repository_name, factoids_named_graph_name)

def add_missing_elements_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri):
    """
    Ajouter des éléments comme les changements, les événements, les attributs et leurs versions
    """

    query = np.query_prefixes + f"""
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

    query = np.query_prefixes + f"""
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


def create_similar_links_for_attributes(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri):
    query = np.query_prefixes + f"""
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

def create_similar_links_for_changes(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri):
    # Create links for similar changes (excepted for attribute changes) : two changes are similar if they are applied to the same element are their type is the same
    query1 = np.query_prefixes + f"""
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
    query2 = np.query_prefixes + f"""
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


def create_similar_links_for_events(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri):
    # Create links for similar events
    query = np.query_prefixes + f"""
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

def create_similar_links_for_temporal_entities(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri):
    # Create links for similar crisp time instants
    query = np.query_prefixes + f"""
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


####################################################################

## Création des sources

def create_source_resource(graphdb_url, repository_name, source_uri:URIRef, source_label:str, publisher_label:str, lang:str, namespace:Namespace, named_graph_uri:URIRef):
    """
    Création de la source relative aux données de la ville de Paris
    """

    source_label_lit = Literal(source_label, lang=lang)
    query = np.query_prefixes + f"""
        INSERT DATA {{
            GRAPH {named_graph_uri.n3()} {{
                {source_uri.n3()} a rico:Record ; rdfs:label {source_label_lit.n3()} .
            }}
        }}
    """
    gd.update_query(query, graphdb_url, repository_name)

    if publisher_label is not None:
        publisher_uri = gr.generate_uri(namespace, "PUB")
        publisher_label_lit = Literal(publisher_label, lang=lang)
        query = np.query_prefixes + f"""
        INSERT DATA {{
            GRAPH {named_graph_uri.n3()} {{
                {source_uri.n3()} rico:hasPublisher {publisher_uri.n3()} .
                {publisher_uri.n3()} a rico:CorporateBody;
                    rdfs:label {publisher_label_lit.n3()}.    
            }}
        }}
        """
        gd.update_query(query, graphdb_url, repository_name)
    
def link_provenances_with_source(graphdb_url, repository_name, source_uri:URIRef, named_graph_uri:URIRef):
    query = np.query_prefixes + f"""
        INSERT {{
            GRAPH {named_graph_uri.n3()} {{
                ?prov rico:isOrWasDescribedBy ?sourceUri .    
            }}
        }} WHERE {{
            BIND({named_graph_uri.n3()} AS ?g)
            BIND({source_uri.n3()} AS ?sourceUri)
            GRAPH ?g {{
                ?prov a prov:Entity .
            }}
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)


def detect_similar_landmarks_with_hidden_label(graphdb_url, repository_name, landmark_type:URIRef, factoids_named_graph_uri):
    # Détection de repères similaires sur le seul critère de similarité du hiddenlabel (il faut qu'ils aient le même type)
    query = np.query_prefixes + f"""
        INSERT {{ 
            GRAPH ?g {{ ?landmark skos:exactMatch ?tmpLandmark . }}
        }}
        WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            {{
                SELECT DISTINCT ?hiddenLabel {{
                    ?tmpLandmark a addr:Landmark; addr:isLandmarkType {landmark_type.n3()} ; skos:hiddenLabel ?hiddenLabel.
                }}
            }}
        BIND(URI(CONCAT(STR(URI(factoids:)), "LM_", STRUUID())) AS ?landmark)
        ?tmpLandmark a addr:Landmark; addr:isLandmarkType {landmark_type.n3()} ; skos:hiddenLabel ?hiddenLabel.
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def remove_temporary_landmarks_and_transfert_triples(graphdb_url:str, repository_name:str, named_graph_uri:str):
    """
    Suppression de landmarks temporaires et transfert de tous ses triplets vers son landmark associé (celui tel que landmark skos:exactMatch landmark tempoaire)
    """
    query = np.query_prefixes + f"""
    DELETE {{
        GRAPH ?g {{
            ?s ?p ?tmpLandmark.
            ?tmpLandmark ?p ?o.
        }}
    }}
    INSERT {{
        GRAPH ?g {{
            ?s ?p ?landmark.
            ?landmark ?p ?o.
        }}
    }}
    WHERE {{
        ?landmark skos:exactMatch ?tmpLandmark.
        GRAPH ?g {{
            {{?tmpLandmark ?p ?o}} UNION {{?s ?p ?tmpLandmark}}
          }}
    }} ; 

    DELETE {{
        ?landmark skos:exactMatch ?tmpLandmark.
    }}
    WHERE {{
        BIND({named_graph_uri.n3()} AS ?g)
        GRAPH ?g {{
            ?landmark skos:exactMatch ?tmpLandmark.
        }}
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)


def add_missing_changes_and_events_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri):
    """
    Ajouter des éléments comme les changements (et événéments associés) manquants pour les repères
    """

    query = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?g {{
                ?change a addr:LandmarkChange ; addr:isChangeType ?cgType ; addr:appliedTo ?landmark ; addr:dependsOn ?event .
                ?event a addr:Event .
            }}
        }} WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            ?landmark a addr:Landmark .
            VALUES ?cgType {{ ctype:LandmarkAppearance ctype:LandmarkDisappearance }}
            MINUS {{?change addr:appliedTo ?landmark ; addr:isChangeType ?cgType . }}
            BIND(URI(CONCAT(STR(URI(factoids:)), "CG_", STRUUID())) AS ?change)
            BIND(URI(CONCAT(STR(URI(factoids:)), "EV_", STRUUID())) AS ?event)
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def add_missing_changes_and_events_for_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri):
    """
    Ajouter des éléments comme les changements (et événéments associés) manquants pour les relations entre repères
    """

    query = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?g {{
                ?change a addr:LandmarkRelationChange ; addr:isChangeType ?cgType ; addr:appliedTo ?landmarkRelation ; addr:dependsOn ?event .
                ?event a addr:Event .
            }}
        }} WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            ?landmarkRelation a addr:LandmarkRelation .
            VALUES ?cgType {{ ctype:LandmarkRelationAppearance ctype:LandmarkRelationDisappearance }}
            MINUS {{ ?change addr:appliedTo ?landmarkRelation ; addr:isChangeType ?cgType . }}
            BIND(URI(CONCAT(STR(URI(factoids:)), "CG_", STRUUID())) AS ?change)
            BIND(URI(CONCAT(STR(URI(factoids:)), "EV_", STRUUID())) AS ?event)
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def add_missing_changes_and_events_for_attributes(graphdb_url, repository_name, factoids_named_graph_uri):
    """
    Ajouter des éléments comme les changements (et événéments associés) manquants pour les attributs (et leurs versions)
    """

    query = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?g {{
                ?change a addr:AttributeChange ; addr:isChangeType ?cgType ; ?predOnVersion ?version ; addr:appliedTo ?attribute ; addr:dependsOn ?event .
                ?event a addr:Event .
            }}
        }} WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            ?attribute a addr:Attribute ; addr:hasAttributeVersion ?version.
            VALUES (?cgType ?predOnVersion) {{
                (ctype:AttributeVersionAppearance addr:makesEffective)
                (ctype:AttributeVersionDisappearance addr:outdates)
                }}
            MINUS {{?change addr:appliedTo ?attribute ; ?predOnVersion ?version ; addr:isChangeType ?cgType . }}
            BIND(URI(CONCAT(STR(URI(factoids:)), "CG_", STRUUID())) AS ?change)
            BIND(URI(CONCAT(STR(URI(factoids:)), "EV_", STRUUID())) AS ?event)
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)


def add_missing_attributes_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri):
    """
    Ajout d'attributs manquants pour les repères à partir des propriétés de base (rdfs:label, geo:asWKT...)
    """

    query = np.query_prefixes + f"""
        INSERT {{ 
            GRAPH ?g {{
                ?landmark addr:hasAttribute ?attr .
                ?attr a addr:Attribute ; addr:isAttributeType ?attrType .
            }}
        }} WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            {{
                SELECT DISTINCT ?landmark ?attr ?attrProp ?attrType 
                WHERE {{
                    VALUES (?attrProp ?attrType) {{ (rdfs:label atype:Name) (geo:asWKT atype:Geometry) (geofla:numInsee atype:InseeCode)}}
                    ?landmark a addr:Landmark ; ?attrProp ?elem .
                    MINUS {{ ?landmark addr:hasAttribute [addr:isAttributeType ?attrType] }}
                }}
            }}
            BIND(URI(CONCAT(STR(URI(factoids:)), "ATTR_", STRUUID())) AS ?attr)
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def add_attributes_version_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri):
    """
    Ajout des versions d'attributs
    """

    query = np.query_prefixes + f"""
        DELETE {{
            ?landmark ?attrProp ?versionValueToRemove
        }}
        INSERT {{
            GRAPH ?g {{
                ?av a addr:AttributeVersion ; addr:versionValue ?versionValue .
                ?attr addr:hasAttributeVersion ?av .
            }}
        }} WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            VALUES (?attrProp ?attrType ?removeTriple) {{
                (rdfs:label atype:Name "false"^^xsd:boolean)
                (geo:asWKT atype:Geometry "true"^^xsd:boolean)
                (geofla:numInsee atype:InseeCode "true"^^xsd:boolean)
            }}
            ?landmark a addr:Landmark ; addr:hasAttribute ?attr ; ?attrProp ?versionValue .
            ?attr a addr:Attribute ; addr:isAttributeType ?attrType .
            BIND(URI(CONCAT(STR(URI(factoids:)), "AV_", STRUUID())) AS ?av)
            BIND(IF(?removeTriple, ?versionValue, ?x) AS ?versionValueToRemove)
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def add_temporal_information_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri):
    """
    Ajout des informations temporelles appliquées au repère
    """

    query = np.query_prefixes + f"""
        DELETE {{
            ?landmark ?lmTimePred ?time .
        }}
        INSERT {{
            GRAPH ?g {{
                ?event ?evTimePred ?time
            }}
        }} WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            VALUES (?lmTimePred ?evTimePred ?cgType) {{
                (addr:hasStartTime addr:hasTime ctype:LandmarkAppearance)
                (addr:hasEarliestStartTime addr:hasTimeAfter ctype:LandmarkAppearance)
                (addr:hasLatestStartTime addr:hasTimeBefore ctype:LandmarkAppearance)
                (addr:hasEndTime addr:hasTime ctype:LandmarkDisappearance)
                (addr:hasEarliestEndTime addr:hasTimeAfter ctype:LandmarkDisappearance)
                (addr:hasLatestEndTime addr:hasTimeBefore ctype:LandmarkDisappearance)
                }}
            ?landmark a addr:Landmark ; ?lmTimePred ?time .
            ?change a addr:Change ; addr:isChangeType ?cgType ; addr:appliedTo ?landmark ; addr:dependsOn ?event .
        }}
        """
    
    gd.update_query(query, graphdb_url, repository_name)

def add_provenances_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri):
    """
    Ajout des liens de provenance des repères vers ses versions d'attributs et les valeurs temporelles
    """

    query = np.query_prefixes + f"""
    INSERT {{
        GRAPH ?g {{ ?elem prov:wasDerivedFrom ?provenance . }}
    }}
    WHERE {{
        BIND({factoids_named_graph_uri.n3()} AS ?g)
        ?landmark a addr:Landmark ; prov:wasDerivedFrom ?provenance .
        {{ ?landmark addr:hasAttribute [addr:hasAttributeVersion ?elem] }}
        UNION
        {{ ?landmark addr:changedBy [addr:dependsOn [addr:hasTime ?elem]] }}
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def update_landmarks(graphdb_url, repository_name, factoids_named_graph_uri):
    """
    Ajouter des éléments comme les changements, les événements, les attributs et leurs versions
    """

    add_missing_changes_and_events_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri)
    add_missing_attributes_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri)
    add_attributes_version_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri)
    add_missing_changes_and_events_for_attributes(graphdb_url, repository_name, factoids_named_graph_uri)
    add_temporal_information_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri)
    add_provenances_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri)
    
def update_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri):
    """
    Ajouter des éléments comme les changements, les événements, les attributs et leurs versions
    """

    add_missing_changes_and_events_for_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri)

def add_missing_temporal_information(graphdb_url, repository_name, factoids_named_graph_uri, time_description:dict):
    """
    Ajout des liens de provenance des repères vers ses versions d'attributs et les valeurs temporelles
    """

    start_time_stamp, start_time_prec, start_time_calendar = tp.get_time_instant_elements(time_description.get("start_time"))
    end_time_stamp, end_time_prec, end_time_calendar = tp.get_time_instant_elements(time_description.get("end_time"))

    values = ""
    start_change_types = ["ctype:AttributeVersionAppearance", "ctype:LandmarkAppearance", "ctype:LandmarkRelationAppearance"]
    end_change_types = ["ctype:AttributeVersionDisappearance", "ctype:LandmarkDisappearance", "ctype:LandmarkRelationDisappearance"]
    for cg_type in start_change_types:
        values += f"({start_time_stamp.n3()} {start_time_prec.n3()} {start_time_calendar.n3()} addr:hasTimeBefore {cg_type})"
    for cg_type in end_change_types:
        values += f"({end_time_stamp.n3()} {end_time_prec.n3()} {end_time_calendar.n3()} addr:hasTimeAfter {cg_type})"

    query = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?g {{
                ?event ?tPred ?timeInstant .
                ?timeInstant a addr:CrispTimeInstant ; addr:timeStamp ?ts ; addr:timePrecision ?tp ; addr:timeCalendar ?tc .
            }}
        }}
        WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            ?cg a addr:Change ; addr:isChangeType ?cgType ; addr:dependsOn ?event .
            MINUS {{ 
                ?event ?p ?t .
                 FILTER(?p IN (addr:hasTime, addr:hasTimeAfter, addr:hasTimeBefore)) }}
            VALUES (?ts ?tp ?tc ?tPred ?cgType) {{
                {values}
            }}
            BIND(URI(CONCAT(STR(URI(factoids:)), "TI_", STRUUID())) AS ?timeInstant)
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def add_other_labels_for_landmark(g:Graph, lm_uri:URIRef, lm_label_value:str, lm_label_lang:str, lm_type_uri:URIRef):
    if lm_type_uri == np.LTYPE["Thoroughfare"]:
        lm_label_type = "thoroughfare"
    elif lm_type_uri in [np.LTYPE["City"], np.LTYPE["District"]]:
        lm_label_type = "area"
    elif lm_type_uri in [np.LTYPE["HouseNumber"],np.LTYPE["StreetNumber"],np.LTYPE["DistrictNumber"],np.LTYPE["PostalCodeArea"]]:
        lm_label_type = "housenumber"
    else:
        lm_label_type = None

    # Ajout de labels alternatif et caché
    alt_label, hidden_label = sp.normalize_and_simplify_name_version(lm_label_value, lm_label_type, lm_label_lang)

    if alt_label is not None:
        alt_label_lit = Literal(alt_label, lang=lm_label_lang)
        g.add((lm_uri, SKOS.altLabel, alt_label_lit))

    if hidden_label is not None:
        hidden_label_lit = Literal(hidden_label, lang=lm_label_lang)
        g.add((lm_uri, SKOS.hiddenLabel, hidden_label_lit))

def transfert_rdflib_graph_to_factoids_repository(graphdb_url, repository_name, factoids_named_graph_name:str, g:Graph, kg_file:str, tmp_folder, ont_file, ontology_named_graph_name):
    g.serialize(kg_file)

    # Création du répertoire
    create_factoid_repository(graphdb_url, repository_name, tmp_folder,
                                ont_file, ontology_named_graph_name, ruleset_name="rdfsplus-optimized",
                                disable_same_as=False, clear_if_exists=True)

    # Import du fichier `ban_kg_file` dans le répertoire
    gd.import_ttl_file_in_graphdb(graphdb_url, repository_name, kg_file, factoids_named_graph_name)

def add_related_time_to_landmark(g:Graph, lm_uri:URIRef, time_stamp:Literal, time_calendar:URIRef, time_precision:URIRef, time_predicate:str):
    """
    `time_predicate` : prédicat liant le repère à l'instant :
    * date de début : `hasStartTime` ;
    * date de début au plus tôt : `hasEarliestStartTime` ;
    * date de début au plus tard : `hasLatestStartTime` ;
    * date de fin : `hasEndTime` ;
    * date de fin au plus tôt : `hasEarliestEndTime` ;
    * date de fin au plus tard : `hasLatestEndTime` ;
    """

    time_uri = gr.generate_uri(np.FACTOIDS, "TI")
    gr.create_crisp_time_instant(g, time_uri, time_stamp, time_calendar, time_precision)
    g.add((lm_uri, np.ADDR[time_predicate], time_uri))