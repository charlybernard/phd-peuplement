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

def merge_landmark_multiple_geometries(graphdb_url, repository_name, factoids_named_graph_uri, geom_kg_file):
    """
    Fusion des géométries d'un landmark si ce dernier en a plus d'une
    """

    to_remove_property = np.ADDR["toRemove"]

    # Requête pour sélectionner toutes les géométries des repères
    query = np.query_prefixes + """
        SELECT DISTINCT * WHERE {
            ?attr addr:isAttributeType atype:Geometry ; addr:hasAttributeVersion ?attrVersion .
            ?attrVersion addr:versionValue ?geom .
            }
        """
    results = gd.select_query_to_json(query, graphdb_url, repository_name)

    attr_geom_values = {}

    for elem in results.get("results").get("bindings"):
        # Récupération des URIs (attibut et version d'attribut) et de la géométrie
        rel_attr = gr.convert_result_elem_to_rdflib_elem(elem.get('attr'))
        rel_attr_version = gr.convert_result_elem_to_rdflib_elem(elem.get('attrVersion'))
        rel_geom = gr.convert_result_elem_to_rdflib_elem(elem.get('geom'))

        if rel_attr in attr_geom_values.keys():
            attr_geom_values[rel_attr].append([rel_attr_version, rel_geom])
        else:
            attr_geom_values[rel_attr] = [[rel_attr_version, rel_geom]]

    # Ajout d'une version de géométrie qui est le résultat de la fusion de l'ensemble des versions liées à un attribut
    # On indique pour chaque version initiale qu'on doit la supprimer.
    g = Graph()
    for attr_uri, versions in attr_geom_values.items():
        if len(versions) > 1:
            geoms = [version[1] for version in versions]
            wkt_literal = gp.get_union_of_geosparql_wktliterals(geoms)
            attr_version_uri = gr.generate_uri(np.FACTOIDS, "AV")
            gr.create_attribute_version(g, attr_version_uri, wkt_literal)
            gr.add_version_to_attribute(g, attr_uri, attr_version_uri)
            for version in versions:
                g.add((version[0], to_remove_property, Literal("true", datatype=XSD.boolean)))

    # Export du graphe dans le fichier `kg_file` qui est importé dans le répertoire
    g.serialize(geom_kg_file)
    gd.import_ttl_file_in_graphdb(graphdb_url, repository_name, geom_kg_file, named_graph_uri=factoids_named_graph_uri)

    query = np.query_prefixes + f"""
        DELETE {{
            ?s ?p ?tmpResource.
            ?tmpResource ?p ?o.
        }}
        WHERE {{
            ?tmpResource {to_remove_property.n3()} ?toRemove.
            FILTER(?toRemove)
            {{?tmpResource ?p ?o}} UNION {{?s ?p ?tmpResource}}
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


def add_time_instants_for_timeless_events(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, time_type:str, stamp:Literal, calendar:URIRef, precision:URIRef):
    if None in [stamp, calendar, precision]:
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

def transfert_factoids_to_facts_repository(graphdb_url, facts_repository_name, factoids_repository_name,
                                           factoids_ttl_file, permanent_ttl_file,
                                           factoids_repo_factoids_named_graph_name, factoids_repo_permanent_named_graph_name,
                                           facts_repo_factoids_named_graph_name, facts_repo_facts_named_graph_name):
    """
    Transfer factoids to facts graph
    """

    gd.export_data_from_repository(graphdb_url, factoids_repository_name, factoids_ttl_file, factoids_repo_factoids_named_graph_name)
    gd.export_data_from_repository(graphdb_url, factoids_repository_name, permanent_ttl_file, factoids_repo_permanent_named_graph_name)
    gd.import_ttl_file_in_graphdb(graphdb_url, facts_repository_name, factoids_ttl_file, facts_repo_factoids_named_graph_name)
    gd.import_ttl_file_in_graphdb(graphdb_url, facts_repository_name, permanent_ttl_file, facts_repo_facts_named_graph_name)

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

def create_root_landmarks(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef, inter_sources_name_graph_uri:URIRef):
    """
    Create `addr:hasRootLandmark` links between similar landmarks.
    """

    create_similar_links_for_areas(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri, inter_sources_name_graph_uri)
    create_similar_links_for_thoroughfares(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri, inter_sources_name_graph_uri)
    create_similar_links_for_housenumbers(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri, inter_sources_name_graph_uri)
    create_similar_links_for_other_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri, inter_sources_name_graph_uri)

def create_similar_links_for_areas(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef, inter_sources_name_graph_uri:URIRef):
    """
    Pour les repères de type DISTRICT, CITY ou POSTALCODEAREA définis dans le graphe nommé `factoids_named_graph_uri`, les lier avec un repère de même type défini dans `facts_named_graph_uri` s'ils ont un nom similaire.
    Le lien créé est mis dans `inter_sources_name_graph_uri`.
    """

    query = np.query_prefixes + f"""
    INSERT {{
        GRAPH ?gf {{ ?rootLandmark a addr:Landmark ; addr:isLandmarkType ?landmarkType ; skos:hiddenLabel ?keyLabel ; rdfs:label ?label . }}
        GRAPH ?gi {{ ?landmark addr:hasRootLandmark ?rootLandmark . }}
    }} WHERE {{
        BIND({facts_named_graph_uri.n3()} AS ?gf)
        BIND({inter_sources_name_graph_uri.n3()} AS ?gi)
        BIND({factoids_named_graph_uri.n3()} AS ?gs)
        {{
            SELECT DISTINCT ?landmarkType ?keyLabel WHERE {{
                ?l a addr:Landmark ; addr:isLandmarkType ?landmarkType ; skos:hiddenLabel ?keyLabel .
                FILTER(?landmarkType IN (ltype:City, ltype:District, ltype:PostalCodeArea))
            }}
        }}
        BIND(URI(CONCAT(STR(URI(facts:)), "LM_", STRUUID())) AS ?toCreateRootLandmark)
        OPTIONAL {{ GRAPH ?gf {{?existingRootLandmark a addr:Landmark ; addr:isLandmarkType ?landmarkType ; skos:hiddenLabel ?keyLabel .}}}}
        BIND(IF(BOUND(?existingRootLandmark), ?existingRootLandmark, ?toCreateRootLandmark) AS ?rootLandmark)
        GRAPH ?gs {{ ?landmark a addr:Landmark . }}
        ?landmark addr:isLandmarkType ?landmarkType ; skos:hiddenLabel ?keyLabel ; rdfs:label ?label .
        MINUS {{ ?landmark addr:hasRootLandmark ?rl . }}
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def create_similar_links_for_thoroughfares(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef, inter_sources_name_graph_uri:URIRef):
    """
    Pour les repères de type VOIE définis dans le graphe nommé `factoids_named_graph_uri`, les lier avec un repère de même type défini dans `facts_named_graph_uri` s'ils ont un nom similaire.
    Le lien créé est mis dans `inter_sources_name_graph_uri`.
    """

    query = np.query_prefixes + f"""
    INSERT {{
        GRAPH ?gf {{ ?rootLandmark a addr:Landmark ; addr:isLandmarkType ?landmarkType ; skos:hiddenLabel ?keyLabel ; rdfs:label ?label . }}
        GRAPH ?gi {{ ?landmark addr:hasRootLandmark ?rootLandmark . }}
    }} WHERE {{
        BIND({facts_named_graph_uri.n3()} AS ?gf)
        BIND({inter_sources_name_graph_uri.n3()} AS ?gi)
        BIND({factoids_named_graph_uri.n3()} AS ?gs)
        {{
            SELECT DISTINCT ?landmarkType ?keyLabel WHERE {{
                ?l a addr:Landmark ; addr:isLandmarkType ?landmarkType ; skos:hiddenLabel ?keyLabel .
                FILTER(?landmarkType IN (ltype:Thoroughfare))
            }}
        }}
        BIND(URI(CONCAT(STR(URI(facts:)), "LM_", STRUUID())) AS ?toCreateRootLandmark)
        OPTIONAL {{ GRAPH ?gf {{?existingRootLandmark a addr:Landmark ; addr:isLandmarkType ?landmarkType ; skos:hiddenLabel ?keyLabel .}}}}
        BIND(IF(BOUND(?existingRootLandmark), ?existingRootLandmark, ?toCreateRootLandmark) AS ?rootLandmark)
        GRAPH ?gs {{ ?landmark a addr:Landmark . }}
        ?landmark addr:isLandmarkType ?landmarkType ; skos:hiddenLabel ?keyLabel ; rdfs:label ?label .
        MINUS {{ ?landmark addr:hasRootLandmark ?rl . }}
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)


def create_similar_links_for_housenumbers(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef, inter_sources_name_graph_uri:URIRef):
    """
    Pour les repères de type HOUSENUMBER définis dans le graphe nommé `factoids_named_graph_uri`, les lier avec un repère de même type défini dans `facts_named_graph_uri` s'ils ont un nom similaire.
    Le lien créé est mis dans `inter_sources_name_graph_uri`.
    """

    query = np.query_prefixes + f"""
    INSERT {{
        GRAPH ?gf {{
            ?rootLandmark a addr:Landmark ; addr:isLandmarkType ?landmarkType ; skos:hiddenLabel ?keyLabel ; rdfs:label ?label .
            ?rootLandmarkRelation a addr:LandmarkRelation ; addr:isLandmarkRelationType ?landmarkRelationType ; addr:locatum ?rootLandmark ; addr:relatum ?rootRelatum .
        }}
        GRAPH ?gi {{
            ?landmark addr:hasRootLandmark ?rootLandmark .
            ?landmarkRelation addr:hasRoot ?rootLandmarkRelation .
        }}
    }}
    WHERE {{
        BIND({facts_named_graph_uri.n3()} AS ?gf)
        BIND({inter_sources_name_graph_uri.n3()} AS ?gi)
        BIND({factoids_named_graph_uri.n3()} AS ?gs)
        {{
            SELECT DISTINCT ?landmarkType ?keyLabel ?landmarkRelationType ?rootRelatum WHERE {{
                ?lr a addr:LandmarkRelation ;
                addr:isLandmarkRelationType ?landmarkRelationType ;
                addr:locatum [a addr:Landmark ; addr:isLandmarkType ?landmarkType ; skos:hiddenLabel ?keyLabel] ;
                addr:relatum [addr:hasRootLandmark ?rootRelatum] .
                FILTER(?landmarkType IN (ltype:HouseNumber, ltype:StreetNumber, ltype:DistrictNumber))
                FILTER(?landmarkRelationType IN (lrtype:Belongs))
            }}
        }}
        BIND(URI(CONCAT(STR(URI(facts:)), "LM_", STRUUID())) AS ?toCreateRootLandmark)
        BIND(URI(CONCAT(STR(URI(facts:)), "LR_", STRUUID())) AS ?toCreateRootLR)
        OPTIONAL {{
            GRAPH ?gf {{
                ?existingRootLandmark a addr:Landmark ; addr:isLandmarkType ?landmarkType ; skos:hiddenLabel ?keyLabel .
                ?existingRootLR a addr:LandmarkRelation ; addr:isLandmarkRelationType ?landmarkRelationType ;
                addr:locatum ?existingRootLandmark ; addr:relatum ?rootRelatum .
            }}
        }}
        BIND(IF(BOUND(?existingRootLandmark), ?existingRootLandmark, ?toCreateRootLandmark) AS ?rootLandmark)
        BIND(IF(BOUND(?existingRootLR), ?existingRootLR, ?toCreateRootLR) AS ?rootLandmarkRelation)
        GRAPH ?gs {{ ?landmark a addr:Landmark . }}
        ?landmark addr:isLandmarkType ?landmarkType ; skos:hiddenLabel ?keyLabel ; rdfs:label ?label .
        ?landmarkRelation a addr:LandmarkRelation ; addr:isLandmarkRelationType ?landmarkRelationType ;
        addr:locatum ?landmark ; addr:relatum [addr:hasRootLandmark ?rootRelatum] .
        MINUS {{ ?landmark addr:hasRootLandmark ?rl . }}
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def create_similar_links_for_other_landmarks(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef, inter_sources_name_graph_uri:URIRef):
    """
    Pour les repères définis dans le graphe nommé `factoids_named_graph_uri` qui ne sont reliés à aucun repère dans le graphe `facts_named_graph_uri`,
    les lier avec un repère de même type créé dans `facts_named_graph_uri`.
    Le lien créé est mis dans `inter_sources_name_graph_uri`.
    """

    query = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?gf {{ ?rootLandmark a addr:Landmark ; addr:isLandmarkType ?landmarkType ; skos:hiddenLabel ?keyLabel ; rdfs:label ?label . }}
            GRAPH ?gi {{ ?landmark addr:hasRootLandmark ?rootLandmark . }}
        }}
        WHERE {{
            BIND({facts_named_graph_uri.n3()} AS ?gf)
            BIND({inter_sources_name_graph_uri.n3()} AS ?gi)
            BIND({factoids_named_graph_uri.n3()} AS ?gs)
            {{
                SELECT DISTINCT ?gs ?landmark WHERE {{ GRAPH ?gs {{ ?landmark a addr:Landmark . }}}}
            }}
            BIND(URI(CONCAT(STR(URI(facts:)), "LM_", STRUUID())) AS ?rootLandmark)
            ?landmark addr:isLandmarkType ?landmarkType .
            OPTIONAL {{ ?landmark rdfs:label ?label }}
            OPTIONAL {{ ?landmark rdfs:label|skos:hiddenLabel ?hiddenLabel }}
            MINUS {{ ?landmark addr:hasRootLandmark ?rl . }}
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def create_root_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef, inter_sources_name_graph_uri:URIRef):
    """
    Pour des relations entre repères dans le graphe nommé `factoids_named_graph_uri`, les lier avec une relation entre repères dans `facts_named_graph_uri` qui sont similaires (mêmes locatum, relatums et type de relation).
    Le lien créé est mis dans `factoids_facts_named_graph_uri`.
    """

    # Création d'un hiddenLabel pour chaque LandmarkRelation du graphe des faits (d'agrégation). Il est composé de la manière suivante : URI du locatum + "&" + URIs ordonnées des relatums séparées d'un point virgule
    # Exemple si une relation a URILoc pour locatum et URIRel1 et URIRel2 comme relatums, le hidden label sera "URILoc1&URIRel1;URIRel2"
    # On crée ce label pour les relations qui n'en n'ont pas
    query1 = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?gf {{?lr skos:hiddenLabel ?hiddenLabel}}
        }} WHERE {{
            {{
                SELECT ?gf ?lr (CONCAT(STR(?rootLoc), "|", GROUP_CONCAT(STR(?rootRel); separator=";")) AS ?hiddenLabel) WHERE {{
                    BIND({facts_named_graph_uri.n3()} AS ?gf)
                    GRAPH ?gf {{ ?lr a addr:LandmarkRelation . }}
                    ?lr addr:relatum ?rootRel ; addr:locatum ?rootLoc .
                }}
                GROUP BY ?gf ?lr ?rootLoc ORDER BY ?rootRel
            }}
        }}
    """

    # On fait la même chose pour les relations du graphe de factoides. On n'intègre pas les URIs des locatums et des relatums mais les URIs de leur racine située dans le graphe des faits.
    query2 = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?gi {{?lr skos:hiddenLabel ?hiddenLabel}}
        }} WHERE {{
            BIND({inter_sources_name_graph_uri.n3()} AS ?gi)
            {{
                SELECT ?gs ?lr (CONCAT(STR(?rootLoc), "|", GROUP_CONCAT(STR(?rootRel); separator=";")) AS ?hiddenLabel) WHERE {{
                    BIND({factoids_named_graph_uri.n3()} AS ?gs)
                    GRAPH ?gs {{ ?lr a ?lrClass . }}
                    ?lrClass rdfs:subClassOf addr:LandmarkRelation .
                    ?lr addr:relatum [addr:hasRootLandmark ?rootRel] ; addr:locatum [addr:hasRootLandmark ?rootLoc] .
                }}
                GROUP BY ?gs ?lr ?rootLoc ORDER BY ?rootRel
            }}
        }}
    """

    query3 = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?gf {{ ?rootLandmarkRelation a addr:LandmarkRelation ; addr:isLandmarkRelationType ?landmarkRelationType ; skos:hiddenLabel ?keyLabel . }}
            GRAPH ?gi {{ ?landmarkRelation addr:hasRoot ?rootLandmarkRelation . }}
        }}
        WHERE {{
            BIND({facts_named_graph_uri.n3()} AS ?gf)
            BIND({inter_sources_name_graph_uri.n3()} AS ?gi)
            BIND({factoids_named_graph_uri.n3()} AS ?gs)
            {{
                SELECT DISTINCT ?landmarkRelationType ?keyLabel WHERE {{
                    ?lr a addr:LandmarkRelation ; addr:isLandmarkRelationType ?landmarkRelationType ; skos:hiddenLabel ?keyLabel .
                }}
            }}
            BIND(URI(CONCAT(STR(URI(facts:)), "LR_", STRUUID())) AS ?toCreateRootLR)
            OPTIONAL {{
                GRAPH ?gf {{ ?existingRootLR a addr:LandmarkRelation }}
                ?existingRootLR skos:hiddenLabel ?keyLabel .
            }}
            BIND(IF(BOUND(?existingRootLR), ?existingRootLR, ?toCreateRootLR) AS ?rootLandmarkRelation)
            GRAPH ?gs {{ ?landmarkRelation a ?lrClass . }}
            ?lrClass rdfs:subClassOf addr:LandmarkRelation .
            ?landmarkRelation addr:isLandmarkRelationType ?landmarkRelationType ; skos:hiddenLabel ?keyLabel .
        }}
    """

    query4 = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?gf {{ ?rootLandmarkRelation ?prop ?rootLandmark . }}
        }}
        WHERE {{
            BIND({facts_named_graph_uri.n3()} AS ?gf)
            GRAPH ?gf {{ ?rootLandmarkRelation a addr:LandmarkRelation .}}
            ?lr addr:hasRoot ?rootLandmarkRelation ; ?prop [addr:hasRootLandmark ?rootLandmark] .
            FILTER (?prop IN (addr:locatum, addr:relatum))
        }}
    """

    queries = [query1, query2, query3, query4]
    for query in queries:
        gd.update_query(query, graphdb_url, repository_name)

def create_root_landmark_attributes(graphdb_url, repository_name, facts_named_graph_uri:URIRef, inter_sources_name_graph_uri:URIRef):
    # Création de root pour les attributs (s'ils n'existent pas)
    query = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?gf {{
                ?rootLm addr:hasAttribute ?rootAttr .
                ?rootAttr a addr:Attribute ; addr:isAttributeType ?attrType.
            }}
            GRAPH ?gi {{
                ?attr addr:hasRoot ?rootAttr .
            }}
        }} WHERE {{
            BIND({facts_named_graph_uri.n3()} AS ?gf)
            BIND({inter_sources_name_graph_uri.n3()} AS ?gi)
            BIND(URI(CONCAT(STR(URI(facts:)), "ATTR_", STRUUID())) AS ?rootAttr)
            {{
                SELECT DISTINCT * WHERE {{
                    ?rootLm addr:isRootOf [addr:hasAttribute [addr:isAttributeType ?attrType]].
                    MINUS {{?rootLm addr:hasAttribute [addr:isAttributeType ?attrType]}}
                }}
            }}
            ?rootLm addr:isRootOf [addr:hasAttribute ?attr] .
            ?attr addr:isAttributeType ?attrType .
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

def link_factoids_with_facts(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, facts_named_graph_uri:URIRef, inter_sources_name_graph_uri:URIRef):
    """
    Landmarks are created as follows:
        * creation of links (using `addr:isSimilarTo`) between landmarks in the facts named graph and those which are in the factoid named graph ;
        * using inference rules, new `addr:isSimilarTo` links are deduced
        * for each resource defined in the factoids, we check whether it exists in the fact graph (if it is linked with a `addr:isSimilarTo` to a resource in the fact graph)
        * for unlinked factoid resources, we create its equivalent in the fact graph
    """

    create_root_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri, inter_sources_name_graph_uri)
    create_root_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri, inter_sources_name_graph_uri)

def import_factoids_in_facts(graphdb_url, repository_name, factoids_named_graph_name, facts_named_graph_name, inter_sources_name_graph_name):
    facts_named_graph_uri = gd.get_named_graph_uri_from_name(graphdb_url, repository_name, facts_named_graph_name)
    factoids_named_graph_uri = gd.get_named_graph_uri_from_name(graphdb_url, repository_name, factoids_named_graph_name)
    inter_sources_name_graph_uri = gd.get_named_graph_uri_from_name(graphdb_url, repository_name, inter_sources_name_graph_name)

    # Ajout de labels normalisés et simplifiés pour les repères (du graphe des factoïdes) afin de faire des liens avec les repères des faits
    add_alt_and_hidden_labels_to_landmarks(graphdb_url, repository_name, factoids_named_graph_uri)

    link_factoids_with_facts(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri, inter_sources_name_graph_uri)

def create_similar_links_for_attributes(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri, inter_sources_name_graph_uri):
    query = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?gi {{ ?attr1 addr:hasRoot ?attr2 . }}
        }}
        WHERE {{
            BIND({facts_named_graph_uri.n3()} AS ?gf)
            BIND({inter_sources_name_graph_uri.n3()} AS ?gi)
            BIND({factoids_named_graph_uri.n3()} AS ?gs)
            GRAPH ?gs {{ ?attr1 a addr:Attribute . }}
            GRAPH ?gf {{ ?attr2 a addr:Attribute . }}
            ?attr1 addr:isAttributeOf ?lm1 ; addr:isAttributeType ?attrType .
            ?attr2 addr:isAttributeOf ?lm2 ; addr:isAttributeType ?attrType .
            ?lm1 addr:hasRoot ?lm2 .
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def create_similar_links_for_changes(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri, inter_sources_name_graph_uri):
    # Create links for similar changes (excepted for attribute changes) : two changes are similar if they are applied to the same element are their type is the same
    query1 = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?gi {{ ?cg1 addr:hasRoot ?cg2 . }}
        }}
        WHERE {{
            BIND({facts_named_graph_uri.n3()} AS ?gf)
            BIND({inter_sources_name_graph_uri.n3()} AS ?gi)
            BIND({factoids_named_graph_uri.n3()} AS ?gs)
            ?changeClass rdfs:subClassOf addr:Change .
            MINUS {{ ?changeClass rdfs:subClassOf addr:AttributeChange }}
            GRAPH ?gs {{ ?cg1 a ?changeClass . }}
            GRAPH ?gf {{ ?cg2 a ?changeClass . }}
            ?cg1 addr:appliedTo ?elem1 ; addr:isChangeType ?cgType .
            ?cg2 addr:appliedTo ?elem2 ; addr:isChangeType ?cgType .
            ?elem1 addr:hasRoot ?elem2 .
        }}
    """

    # Create links for similar attribute changes
    query2 = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?gi {{ ?cg1 addr:hasRoot ?cg2 . }}
        }}
        WHERE {{
            BIND({facts_named_graph_uri.n3()} AS ?gf)
            BIND({inter_sources_name_graph_uri.n3()} AS ?gi)
            BIND({factoids_named_graph_uri.n3()} AS ?gs)
            ?changeClass rdfs:subClassOf addr:AttributeChange .
            GRAPH ?gs {{
                ?cg1 a ?changeClass .
                ?av1 a addr:AttributeVersion .
                }}
            GRAPH ?gf {{
                ?cg2 a ?changeClass .
                ?av2 a addr:AttributeVersion .
                }}
            ?cg1 ?p ?av1 .
            ?cg2 ?p ?av2 .
            FILTER (?p IN (addr:makesEffective, addr:outdates))
            ?av1 addr:hasRoot ?av2 .
        }}
    """

    queries = [query1, query2]
    for query in queries:
        gd.update_query(query, graphdb_url, repository_name)


def create_similar_links_for_events(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri, inter_sources_name_graph_uri):
    # Create links for similar events
    query = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?gi {{ ?ev1 addr:hasRoot ?ev2 . }}
        }}
        WHERE {{
            BIND({facts_named_graph_uri.n3()} AS ?gf)
            BIND({inter_sources_name_graph_uri.n3()} AS ?gi)
            BIND({factoids_named_graph_uri.n3()} AS ?gs)
            GRAPH ?gs {{ ?ev1 a addr:Event . }}
            GRAPH ?gf {{ ?ev2 a addr:Event . }}
            ?cg1 addr:dependsOn ?ev1 .
            ?cg2 addr:dependsOn ?ev2 .
            ?cg1 addr:hasRoot ?cg2 .
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def create_similar_links_for_temporal_entities(graphdb_url, repository_name, factoids_named_graph_uri, facts_named_graph_uri, inter_sources_name_graph_uri):
    # Create links for similar crisp time instants
    query = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?gi {{
                ?t1 addr:hasRoot ?t2.
            }}
        }}
        WHERE {{
            BIND({facts_named_graph_uri.n3()} AS ?gf)
            BIND({inter_sources_name_graph_uri.n3()} AS ?gi)
            BIND({factoids_named_graph_uri.n3()} AS ?gs)
            GRAPH ?gs {{
                ?ev1 a addr:Event ; ?p ?t1 .
                ?t1 a addr:CrispTimeInstant .
                }}
            GRAPH ?gf {{
                ?ev2 a addr:Event ; ?p ?t2 .
                ?t2 a addr:CrispTimeInstant .
                }}
            FILTER (?p IN (addr:hasTime, addr:hasTimeBefore, addr:hasTimeAfter))
            ?t1 addr:timeStamp ?timeStamp ; addr:timeCalendar ?timeCal ; addr:timePrecision ?timePrec .
            ?t2 addr:timeStamp ?timeStamp ; addr:timeCalendar ?timeCal ; addr:timePrecision ?timePrec .
            ?ev1 addr:hasRoot ?ev2 .
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


def create_landmark_version(g:Graph, lm_uri:URIRef, lm_type_uri:URIRef, lm_label:str, attr_types_and_values:list[list], time_description:dict, factoids_namespace:Namespace, lang:str):
    gr.create_landmark(g, lm_uri, lm_label, lang, lm_type_uri)

    for attr in attr_types_and_values:
        attr_type_uri, attr_value_lit = attr
        attr_uri, attr_version_uri = gr.generate_uri(factoids_namespace, "ATTR"), gr.generate_uri(factoids_namespace, "AV")
        gr.create_landmark_attribute_and_version(g, lm_uri, attr_uri, attr_type_uri, attr_version_uri, attr_value_lit)

    add_other_labels_for_landmark(g, lm_uri, lm_label, lang, lm_type_uri)
    add_validity_time_interval_to_landmark(g, lm_uri, time_description)


def detect_similar_landmarks_with_hidden_label_and_landmark_relation(graphdb_url, repository_name, similar_property:URIRef, landmark_type:URIRef, landmark_relation_type:URIRef, factoids_named_graph_uri:URIRef):
    # Détection de repères similaires sur le seul critère de similarité du hiddenlabel et d'appartenance à un même repère (il faut qu'ils aient le même type)
    query = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?g {{ ?landmark {similar_property.n3()} ?tmpLandmark . }}
        }}
        WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            {{
                SELECT DISTINCT ?hiddenLabel ?belongsLandmark {{
                    ?tmpLandmark a addr:Landmark; addr:isLandmarkType {landmark_type.n3()} ; skos:hiddenLabel ?hiddenLabel .
                    ?lr a addr:LandmarkRelation ; addr:isLandmarkRelationType {landmark_relation_type.n3()}; addr:locatum ?tmpLandmark ; addr:relatum ?belongsLandmark .
                }}
            }}
        BIND(URI(CONCAT(STR(URI(factoids:)), "LM_", STRUUID())) AS ?landmark)
        ?tmpLandmark a addr:Landmark; addr:isLandmarkType {landmark_type.n3()} ; skos:hiddenLabel ?hiddenLabel.
        ?lr a addr:LandmarkRelation ; addr:isLandmarkRelationType {landmark_relation_type.n3()}; addr:locatum ?tmpLandmark ; addr:relatum ?belongsLandmark .
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def detect_similar_landmarks_with_hidden_label(graphdb_url, repository_name, similar_property:URIRef, landmark_type:URIRef, factoids_named_graph_uri:URIRef):
    # Détection de repères similaires sur le seul critère de similarité du hiddenlabel (il faut qu'ils aient le même type)
    query = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?g {{ ?landmark {similar_property.n3()} ?tmpLandmark . }}
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


def detect_similar_attributes(graphdb_url, repository_name, similar_property:URIRef, factoids_named_graph_uri:URIRef):
    # Détection des attributs similaires à partir de la requête précedente
    query = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?g {{
                ?attr {similar_property.n3()} ?tmpAttr .
            }}
        }} WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            {{
                SELECT DISTINCT ?lm ?attrType WHERE {{
                    ?lm addr:hasAttribute [addr:isAttributeType ?attrType] .
                }}
            }}
            BIND(URI(CONCAT(STR(URI(factoids:)), "ATTR_", STRUUID())) AS ?attr)
            ?lm addr:hasAttribute ?tmpAttr .
            ?tmpAttr addr:isAttributeType ?attrType .
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)


def detect_similar_attribute_versions(graphdb_url, repository_name, similar_property:URIRef, factoids_named_graph_uri:URIRef):

    query = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?g {{
                ?av {similar_property.n3()} ?tmpAv .
            }}
        }} WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            {{
                SELECT DISTINCT ?attr ?versionValue WHERE {{
                    ?attr addr:hasAttributeVersion [addr:versionValue ?versionValue] .
                }}
            }}
            BIND(URI(CONCAT(STR(URI(factoids:)), "AV_", STRUUID())) AS ?av)
            ?attr addr:hasAttributeVersion ?tmpAv .
            ?tmpAv addr:versionValue ?versionValue .
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def detect_similar_landmark_relations(graphdb_url, repository_name, similar_property:URIRef, factoids_named_graph_uri:URIRef):
    query = np.query_prefixes + f"""
    INSERT {{
        GRAPH {factoids_named_graph_uri.n3()} {{
            ?lr1 {similar_property.n3()} ?lr2 .
        }}
    }}
    WHERE {{
        BIND({factoids_named_graph_uri.n3()} AS ?gs)
        ?lr1 a addr:LandmarkRelation ; addr:isLandmarkRelationType ?lrtype ; addr:locatum ?loc ; addr:relatum ?rel .
        ?lr2 a addr:LandmarkRelation ; addr:isLandmarkRelationType ?lrtype ; addr:locatum ?loc ; addr:relatum ?rel .
        FILTER (!sameTerm(?lr1, ?lr2))
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def merge_similar_landmarks_with_hidden_labels(graphdb_url, repository_name, landmark_type:URIRef, factoids_named_graph_uri:URIRef):
    similar_property = np.SKOS["exactMatch"]

    # Détection de repères similaires et fusion
    detect_similar_landmarks_with_hidden_label(graphdb_url, repository_name, similar_property, landmark_type, factoids_named_graph_uri)
    remove_temporary_resources_and_transfert_triples(graphdb_url, repository_name, similar_property, factoids_named_graph_uri)

    # Détection des attributs similaires et fusion
    detect_similar_attributes(graphdb_url, repository_name, similar_property, factoids_named_graph_uri)
    remove_temporary_resources_and_transfert_triples(graphdb_url, repository_name, similar_property, factoids_named_graph_uri)

    # Détection des versions d'attribut similaires et fusion
    detect_similar_attribute_versions(graphdb_url, repository_name, similar_property, factoids_named_graph_uri)
    remove_temporary_resources_and_transfert_triples(graphdb_url, repository_name, similar_property, factoids_named_graph_uri)

def merge_similar_landmarks_with_hidden_label_and_landmark_relation(graphdb_url, repository_name, landmark_type:URIRef, landmark_relation_type:URIRef, factoids_named_graph_uri:URIRef):
    similar_property = np.SKOS["exactMatch"]

    # Détection de repères similaires et fusion
    detect_similar_landmarks_with_hidden_label_and_landmark_relation(graphdb_url, repository_name, similar_property, landmark_type, landmark_relation_type, factoids_named_graph_uri)
    remove_temporary_resources_and_transfert_triples(graphdb_url, repository_name, similar_property, factoids_named_graph_uri)

    # Détection des attributs similaires et fusion
    detect_similar_attributes(graphdb_url, repository_name, similar_property, factoids_named_graph_uri)
    remove_temporary_resources_and_transfert_triples(graphdb_url, repository_name, similar_property, factoids_named_graph_uri)

    # Détection des versions d'attribut similaires et fusion
    detect_similar_attribute_versions(graphdb_url, repository_name, similar_property, factoids_named_graph_uri)
    remove_temporary_resources_and_transfert_triples(graphdb_url, repository_name, similar_property, factoids_named_graph_uri)

def merge_similar_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri:URIRef):
    similar_property = np.SKOS["exactMatch"]

    # Détection de repères similaires et fusion
    detect_similar_landmark_relations(graphdb_url, repository_name, similar_property, factoids_named_graph_uri)
    remove_temporary_resources_and_transfert_triples(graphdb_url, repository_name, similar_property, factoids_named_graph_uri)

def detect_similar_time_interval_of_landmarks(graphdb_url, repository_name, similar_property, factoids_named_graph_uri:URIRef):
    query1 = np.query_prefixes  + f"""
        INSERT {{
            ?lm addr:hasTime ?time .
            ?time a addr:TemporaryTime .
        }}
        WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            {{
                SELECT DISTINCT ?lm ?time WHERE {{
                    ?lm a addr:Landmark .
                }}
            }}
            BIND(URI(CONCAT(STR(URI(factoids:)), "TI_", STRUUID())) AS ?time)
        }} ;

        DELETE {{
            ?time a addr:TemporaryTime .
            ?lm addr:hasTime ?time .
        }}
        INSERT {{
            GRAPH ?g {{ ?time {similar_property.n3()} ?tmpTime . }}
        }}
        WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            ?lm addr:hasTime ?tmpTime , ?time .
            ?time a addr:TemporaryTime .
            FILTER(?tmpTime != ?time)
        }}
    """

    query2 = np.query_prefixes + f"""
        INSERT {{
            GRAPH ?g {{ ?time {similar_property.n3()} ?tmpTime . }}
        }}
        WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
        {{
            SELECT DISTINCT ?propTime ?timeStamp ?timeCal ?timePrec WHERE {{
                ?interval a addr:CrispTimeInterval ; ?propTime ?time .
                FILTER(?propTime IN (addr:hasBeginning, addr:hasEnd))
                ?time addr:timeStamp ?timeStamp ; addr:timeCalendar ?timeCal ; addr:timePrecision ?timePrec .
            }}
        }}
        BIND(URI(CONCAT(STR(URI(factoids:)), "TI_", STRUUID())) AS ?time)
        ?interval a addr:CrispTimeInterval ; ?propTime ?tmpTime.
    }}
    """

    queries = [query1, query2]
    for query in queries:
        gd.update_query(query, graphdb_url, repository_name)
        remove_temporary_resources_and_transfert_triples(graphdb_url, repository_name, np.SKOS["exactMatch"], factoids_named_graph_uri)


def remove_temporary_resources_and_transfert_triples(graphdb_url:str, repository_name:str, similar_property:URIRef, named_graph_uri:str):
    """
    Suppression de ressources temporaires et transfert de tous ses triplets vers sa resource associée (celui tel que resource skos:exactMatch resource tempoaire)
    """
    query = np.query_prefixes + f"""
    DELETE {{
        GRAPH ?g {{
            ?s ?p ?tmpResource.
            ?tmpResource ?p ?o.
        }}
    }}
    INSERT {{
        GRAPH ?g {{
            ?s ?p ?resource.
            ?resource ?p ?o.
        }}
    }}
    WHERE {{
        ?resource {similar_property.n3()} ?tmpResource.
        GRAPH ?g {{
            {{?tmpResource ?p ?o}} UNION {{?s ?p ?tmpResource}}
          }}
    }} ;

    DELETE {{
        ?resource {similar_property.n3()} ?tmpResource.
    }}
    WHERE {{
        BIND({named_graph_uri.n3()} AS ?g)
        GRAPH ?g {{
            ?resource {similar_property.n3()} ?tmpResource.
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

    # add_missing_changes_and_events_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri)
    add_missing_attributes_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri)
    add_attributes_version_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri)
    # add_missing_changes_and_events_for_attributes(graphdb_url, repository_name, factoids_named_graph_uri)
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

    start_time_stamp, start_time_calendar, start_time_prec = tp.get_time_instant_elements(time_description.get("start_time"))
    end_time_stamp, end_time_calendar, end_time_prec = tp.get_time_instant_elements(time_description.get("end_time"))

    values = ""
    start_change_types = ["ctype:AttributeVersionAppearance", "ctype:LandmarkAppearance", "ctype:LandmarkRelationAppearance"]
    end_change_types = ["ctype:AttributeVersionDisappearance", "ctype:LandmarkDisappearance", "ctype:LandmarkRelationDisappearance"]
    for cg_type in start_change_types:
        values += f"({start_time_stamp.n3()} {start_time_calendar.n3()} {start_time_prec.n3()} addr:hasTimeBefore {cg_type})"
    for cg_type in end_change_types:
        values += f"({end_time_stamp.n3()} {end_time_calendar.n3()} {end_time_prec.n3()} addr:hasTimeAfter {cg_type})"

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
            VALUES (?ts ?tc ?tp ?tPred ?cgType) {{
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

    # Import du fichier `kg_file` dans le répertoire
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

def add_validity_time_interval_to_landmark(g:Graph, lm_uri:URIRef, time_description:dict):
    start_time_stamp, start_time_calendar, start_time_precision = tp.get_time_instant_elements(time_description.get("start_time"))
    end_time_stamp, end_time_calendar, end_time_precision = tp.get_time_instant_elements(time_description.get("end_time"))
    time_interval_uri, start_time_uri, end_time_uri = gr.generate_uri(np.FACTOIDS, "TI"), gr.generate_uri(np.FACTOIDS, "TI"), gr.generate_uri(np.FACTOIDS, "TI")

    gr.create_crisp_time_instant(g, start_time_uri, start_time_stamp, start_time_calendar, start_time_precision)
    gr.create_crisp_time_instant(g, end_time_uri, end_time_stamp, end_time_calendar, end_time_precision)
    gr.create_crisp_time_interval(g, time_interval_uri, start_time_uri, end_time_uri)
    gr.add_time_to_resource(g, lm_uri, time_interval_uri)