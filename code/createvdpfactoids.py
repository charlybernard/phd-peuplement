import filemanagement as fm
import json
import multisourcesprocessing as msp
import geomprocessing as gp
import strprocessing as sp
import timeprocessing as tp
from rdflib import Graph, Namespace, Literal, BNode, URIRef
from rdflib.namespace import RDF, XSD, RDFS, SKOS
import graphrdf as gr
import graphdb as gd
import re

def split_cell_content(cell_content:str, sep=",", remove_spaces=True):
    if cell_content == "" or cell_content is None:
        return []
    
    elems = cell_content.split(sep)
    if remove_spaces:
        return [re.sub("(^ {1,}| {1,}$)", "", x) for x in elems]
    return elems

def get_vpc_column_indices(header):
    id_col = "Identifiant"
    name_col = "Dénomination complète minuscule"
    start_time_col = "Date de l'arrêté"
    end_time_col = "Date de caducité"
    arrdt_col = "Arrondissement"
    district_col = "Quartier"

    id_col_index = header.index(id_col)
    name_col_index = header.index(name_col)
    start_time_col_index = header.index(start_time_col)
    end_time_col_index = header.index(end_time_col)
    arrdt_col_index = header.index(arrdt_col)
    district_col_index = header.index(district_col)

    col_indices = {"id": id_col_index ,"name":name_col_index, "start_time":start_time_col_index, "end_time":end_time_col_index, "arrdt":arrdt_col_index, "district":district_col_index}

    return col_indices

def get_vpa_column_indices(header):
    id_col = "Identifiant"
    name_col = "Dénomination complète minuscule"
    start_time_col = "Date de l'arrété"
    arrdt_col = "Arrondissement"
    district_col = "Quartier"
    geom_col = "geo_shape"

    id_col_index = header.index(id_col)
    name_col_index = header.index(name_col)
    start_time_col_index = header.index(start_time_col)
    arrdt_col_index = header.index(arrdt_col)
    district_col_index = header.index(district_col)
    geom_col_index = header.index(geom_col)

    col_indices = {"id": id_col_index ,"name":name_col_index, "start_time":start_time_col_index, "arrdt":arrdt_col_index, "district":district_col_index, "geom":geom_col_index}

    return col_indices

def create_source_ville_paris(graphdb_url, repository_name, source_uri:URIRef, named_graph_uri:URIRef, query_prefixes:str):
    """
    Création de la source relative aux données de la ville de Paris
    """

    source_label = Literal("dénomination des voies de Paris (actuelles et caduques)", lang="fr")
    publisher_uri = namespace_prefixes["facts"]["DirTopoDocFoncVP"]
    publisher_label = Literal("Département de la Topographie et de la Documentation Foncière de la Ville de Paris", lang="fr")

    query = query_prefixes + f"""
        INSERT DATA {{
            GRAPH {named_graph_uri.n3()} {{
                {source_uri.n3()} a rico:Record;
                    rdfs:label {source_label.n3()} ;
                    rico:hasPublisher {publisher_uri.n3()} .
                {publisher_uri.n3()} a rico:CorporateBody;
                    rdfs:label {publisher_label.n3()}.    
            }}
        }}
    """
    
    gd.update_query(query, graphdb_url, repository_name)

def link_provenances_with_source(graphdb_url, repository_name, source_uri:URIRef, named_graph_uri:URIRef, query_prefixes:str):
    query = query_prefixes + f"""
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


def create_graph_of_former_thoroughfares(vpc_file, source_time_description, namespace_prefixes:dict, lang:str):
    vpc_pref, vpc_ns = "vdpc", Namespace("https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/denominations-des-voies-caduques/records/")
    
    header, rows = fm.read_csv_file(vpc_file, has_header=True, delimiter=";", encoding='utf-8-sig')
    col_indices = get_vpc_column_indices(header)
    g = Graph()
    gr.add_namespaces_to_graph(g, namespace_prefixes)
    g.bind(vpc_pref, vpc_ns)

    for row in rows:
        th_id = row[col_indices.get("id")]
        th_label = row[col_indices.get("name")]
        th_start_time = row[col_indices.get("start_time")]
        th_end_time = row[col_indices.get("end_time")]
        th_arrdts = split_cell_content(row[col_indices.get("arrdt")], sep=",")
        th_districts = split_cell_content(row[col_indices.get("district")], sep=",")

        create_former_thoroughfare(g, th_id, th_label, th_start_time, th_end_time, th_arrdts, th_districts, source_time_description, vpc_ns, namespace_prefixes, lang)

    return g

def create_former_thoroughfare(g:Graph, id:str, label:str, start_time_stamp:str, end_time_stamp:str, arrdts:list, districts:list, source_time_description, vpa_ns:Namespace, namespace_prefixes:dict, lang:str):
    """
    `source_time_description` : dictionnaire décrivant les dates de début et de fin de validité de la source
    `source_time_description = {"start_time":{"stamp":..., "precision":..., "calendar":...}, "end_time":{} }`
    """

    th_prov_uri = vpa_ns[id]
    th_uri = gr.generate_uri(namespace_prefixes["factoids"], "TH")

    # Création basique de la voie (on indique le type de repère et on y ajoute un label)
    gr.create_landmark(g, th_uri, label, lang, "Thoroughfare", namespace_prefixes["addr"], namespace_prefixes["ltype"])

    # Ajout de la provenance du repère 
    create_thoroughfare_provenance(g, th_uri, th_prov_uri, namespace_prefixes)

    # Ajout d'informations temporelles    
    start_time_stamp, start_time_calendar, start_time_precision, start_time_pred = get_thoroughfare_start_time(start_time_stamp, source_time_description)
    end_time_stamp, end_time_precision, end_time_calendar, end_time_pred = get_former_thoroughfare_end_time(end_time_stamp, source_time_description)

    create_thoroughfare_related_time(g, th_uri, start_time_stamp, start_time_calendar, start_time_precision, start_time_pred)
    create_thoroughfare_related_time(g, th_uri, end_time_stamp, end_time_calendar, end_time_precision, end_time_pred)

    # Création des arrondissements et des quartiers liés à la voie + ajout de la relation spatiale avec la voie
    create_thoroughfare_arrondissements_and_relations(g, th_uri, arrdts, th_prov_uri, namespace_prefixes, lang)
    create_thoroughfare_districts_and_relations(g, th_uri, districts, th_prov_uri, namespace_prefixes, lang)

    add_other_labels_for_landmark(g, th_uri, label, "thoroughfare", lang)

def create_graph_of_current_thoroughfares(vpa_file, source_time_description, namespace_prefixes:dict, lang:str):
    vpa_pref, vpa_ns = "vdpa", Namespace("https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/denominations-emprises-voies-actuelles/records/")
    
    header, rows = fm.read_csv_file(vpa_file, has_header=True, delimiter=";", encoding='utf-8-sig')
    col_indices = get_vpa_column_indices(header)
    g = Graph()
    gr.add_namespaces_to_graph(g, namespace_prefixes)
    g.bind(vpa_pref, vpa_ns)

    source_time_description = tp.get_valid_time_description(source_time_description)

    for row in rows:
        th_id = row[col_indices.get("id")]
        th_label = row[col_indices.get("name")]
        th_geom = row[col_indices.get("geom")]
        th_start_time = row[col_indices.get("start_time")]
        th_arrdts = split_cell_content(row[col_indices.get("arrdt")], sep=",")
        th_districts = split_cell_content(row[col_indices.get("district")], sep=",")

        create_current_thoroughfare(g, th_id, th_label, th_geom, th_start_time, th_arrdts, th_districts, source_time_description, vpa_ns, namespace_prefixes, lang)

    return g

def create_current_thoroughfare(g:Graph, id:str, label:str, geom:str, start_time_stamp:str, arrdts:list, districts:list, source_time_description, vpa_ns:Namespace, namespace_prefixes:dict, lang:str):
    """
    `source_time_description` : dictionnaire décrivant les dates de début et de fin de validité de la source
    `source_time_description = {"start_time":{"stamp":..., "precision":..., "calendar":...}, "end_time":{} }`
    """

    th_prov_uri = vpa_ns[id]
    th_uri = gr.generate_uri(namespace_prefixes["factoids"], "TH")

    # Création basique de la voie (on indique le type de repère et on y ajoute un label)
    gr.create_landmark(g, th_uri, label, lang, "Thoroughfare", namespace_prefixes["addr"], namespace_prefixes["ltype"])

    # Ajout de la provenance du repère 
    create_thoroughfare_provenance(g, th_uri, th_prov_uri, namespace_prefixes)

    # Création d'une géométrie
    create_thoroughfare_geometry(g, th_uri, geom)

    # Ajout d'informations temporelles    
    start_time_stamp, start_time_calendar, start_time_precision, start_time_pred = get_thoroughfare_start_time(start_time_stamp, source_time_description)
    end_time_stamp, end_time_precision, end_time_calendar = tp.get_time_instant_elements(source_time_description.get("end_time"))
    end_time_pred = "hasEarliestEndTime"

    create_thoroughfare_related_time(g, th_uri, start_time_stamp, start_time_calendar, start_time_precision, start_time_pred)
    create_thoroughfare_related_time(g, th_uri, end_time_stamp, end_time_calendar, end_time_precision, end_time_pred)

    # Création des arrondissements et des quartiers liés à la voie + ajout de la relation spatiale avec la voie
    create_thoroughfare_arrondissements_and_relations(g, th_uri, arrdts, th_prov_uri, namespace_prefixes, lang)
    create_thoroughfare_districts_and_relations(g, th_uri, districts, th_prov_uri, namespace_prefixes, lang)

    add_other_labels_for_landmark(g, th_uri, label, "thoroughfare", lang)

def get_gregorian_date_from_timestamp(time_stamp):
    time_match_pattern = "^\d{4}\-(0?[1-9]|1[012])\-(0?[1-9]|[12][0-9]|3[01])$"
    if re.match(time_match_pattern, time_stamp) is not None:
        time_stamp += "T00:00:00Z"
        time_description = {"stamp":time_stamp, "calendar":"gregorian", "precision":"day"}
        time_elements = tp.get_time_instant_elements(time_description)

        return time_elements
    
    return [None, None, None]

def get_thoroughfare_start_time(start_time_stamp, source_time_description):
    time_elements = get_gregorian_date_from_timestamp(start_time_stamp)
    if None in time_elements:
        start_time_stamp, start_time_precision, start_time_calendar = tp.get_time_instant_elements(source_time_description.get("start_time"))
        start_time_pred = "hasLatestStartTime"
    else:
        start_time_stamp, start_time_precision, start_time_calendar = time_elements
        start_time_pred = "hasStartTime"
        
    return start_time_stamp, start_time_calendar, start_time_precision, start_time_pred

def get_former_thoroughfare_end_time(start_time_stamp, source_time_description):
    time_elements = get_gregorian_date_from_timestamp(start_time_stamp)
    if None in time_elements:
        start_time_stamp, start_time_precision, start_time_calendar = tp.get_time_instant_elements(source_time_description.get("start_time"))
        start_time_pred = "hasLatestEndTime"
    else:
        start_time_stamp, start_time_precision, start_time_calendar = time_elements
        start_time_pred = "hasEndTime"
        
    return start_time_stamp, start_time_calendar, start_time_precision, start_time_pred

def create_thoroughfare_provenance(g:Graph, th_uri:URIRef, th_prov_uri:URIRef, namespace_prefixes:dict):
    g.add((th_uri, namespace_prefixes["prov"]["wasDerivedFrom"], th_prov_uri))
    g.add((th_prov_uri, RDF.type, namespace_prefixes["prov"]["Entity"]))

def create_thoroughfare_geometry(g:Graph, th_uri:URIRef, geojson_str:str):
    # Gestion de la géométrie
    ## * Récupération de la géométrie en WKT
    ## * conversion en un geo:wktLiteral
    ## * ajout du triplet <landmark geo:asWKT geom> dans le graph
    geom = json.loads(geojson_str)
    wkt_geom = gp.from_geojson_to_wkt(geom)
    th_geom_lit = Literal(wkt_geom, datatype=namespace_prefixes["geo"]["wktLiteral"])
    g.add((th_uri, namespace_prefixes["geo"]["asWKT"], th_geom_lit))

def create_thoroughfare_related_time(g:Graph, th_uri:URIRef, time_stamp:Literal, time_calendar:URIRef, time_precision:URIRef, time_predicate:str):
    """
    `time_predicate` : prédicat liant le repère à l'instant :
    * date de début : `hasStartTime` ;
    * date de début au plus tôt : `hasEarliestStartTime` ;
    * date de début au plus tard : `hasLatestStartTime` ;
    * date de fin : `hasEndTime` ;
    * date de fin au plus tôt : `hasEarliestEndTime` ;
    * date de fin au plus tard : `hasLatestEndTime` ;
    """

    time_uri = gr.generate_uri(namespace_prefixes["factoids"], "TI")
    gr.create_crisp_time_instant(g, time_uri, time_stamp, time_calendar, time_precision, namespace_prefixes["addr"])
    g.add((th_uri, namespace_prefixes["addr"][time_predicate], time_uri))

def create_thoroughfare_area_and_relation(g:Graph, th_uri:URIRef, area_uri:URIRef, area_name:str, area_type:str, th_prov_uri:URIRef, namespace_prefixes:dict, lang:str):
    """"
    Création d'une zone (quartier, arrondissement, commune) à laquelle appartient la voie et ajout de la relation entre les deux entités géographiques (Within)
    """

    gr.create_landmark(g, area_uri, area_name, lang, area_type, namespace_prefixes["addr"], namespace_prefixes["ltype"])
    lr_uri = gr.generate_uri(namespace_prefixes["factoids"], "LR")
    gr.create_landmark_relation(g, lr_uri, th_uri, [area_uri], "Within", namespace_prefixes["addr"], namespace_prefixes["lrtype"])
    add_other_labels_for_landmark(g, area_uri, area_name, "area", lang)

    # L'existence de la zone et de la relation entre les deux entités géographique est sourcé par `th_prov_uri`
    g.add((area_uri, namespace_prefixes["prov"]["wasDerivedFrom"], th_prov_uri))
    g.add((lr_uri, namespace_prefixes["prov"]["wasDerivedFrom"], th_prov_uri))

def create_thoroughfare_arrondissements_and_relations(g:Graph, th_uri:URIRef, arrdts:list, th_prov_uri:URIRef, namespace_prefixes:dict, lang:str):
    for arrdt in arrdts:
        arrdt_uri = gr.generate_uri(namespace_prefixes["factoids"], "ARRDT")
        arrdt_label = re.sub("^0", "", arrdt.replace("01e", "01er")) + " arrondissement de Paris"
        create_thoroughfare_area_and_relation(g, th_uri, arrdt_uri, arrdt_label, "District", th_prov_uri, namespace_prefixes, lang)

def create_thoroughfare_districts_and_relations(g:Graph, th_uri:URIRef, districts:list, th_prov_uri:URIRef, namespace_prefixes:dict, lang:str):
    for district in districts:
        district_uri = gr.generate_uri(namespace_prefixes["factoids"], "DIST")
        create_thoroughfare_area_and_relation(g, th_uri, district_uri, district, "District", th_prov_uri, namespace_prefixes, lang)

def add_other_labels_for_landmark(g:Graph, lm_uri:URIRef, lm_label_value:str, lm_label_type:str, lm_label_lang):
    # Ajout de labels alternatif et caché
    alt_label, hidden_label = sp.normalize_and_simplify_name_version(lm_label_value, lm_label_type, lm_label_lang)
    alt_label_lit = Literal(alt_label, lang=lang)
    hidden_label_lit = Literal(hidden_label, lang=lang)
    g.add((lm_uri, SKOS.altLabel, alt_label_lit))
    g.add((lm_uri, SKOS.hiddenLabel, hidden_label_lit))

def clean_vdp_repository(graphdb_url:str, repository_name:str, source_time_description:dict, factoids_named_graph_name:str, permanent_named_graph_name:str, namespace_prefixes:dict):
    query_prefixes = gd.get_query_prefixes_from_namespaces(namespace_prefixes)
    factoids_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, factoids_named_graph_name))
    permanent_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, permanent_named_graph_name))

    # Fusion des repères similaires
    detect_similar_areas(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes)
    remove_temporary_landmarks_and_transfert_triples(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes)

    # Ajout d'éléments manquants comme les changements, événements, attributs, versions d'attributs
    update_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes)
    update_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes)

    source_time_description = tp.get_valid_time_description(source_time_description)
    add_missing_temporal_information(graphdb_url, repository_name, factoids_named_graph_uri, source_time_description, query_prefixes)

    # Transférer toutes les descriptions de provenance vers le graphe nommé permanent
    msp.transfert_immutable_triples(graphdb_url, repository_name, factoids_named_graph_uri, permanent_named_graph_uri)

    # L'URI ci-dessous définit la source liée à la ville de Paris
    vdp_source_uri = namespace_prefixes["facts"]["Source_VDP"]
    create_source_ville_paris(graphdb_url, repository_name, vdp_source_uri, permanent_named_graph_uri, query_prefixes)
    link_provenances_with_source(graphdb_url, repository_name, vdp_source_uri, permanent_named_graph_uri, query_prefixes)


def detect_similar_areas(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes):
    # Détection des quartiers et arrondissements similaires (ils ont le même hiddenlabel)
    query = query_prefixes + f"""
        INSERT {{ 
            GRAPH ?g {{ ?landmark skos:exactMatch ?tmpLandmark . }}
        }}
        WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            {{
                SELECT DISTINCT ?hiddenLabel {{
                    ?tmpLandmark a addr:Landmark; addr:isLandmarkType ltype:District ; skos:hiddenLabel ?hiddenLabel.
                }}
            }}
        BIND(URI(CONCAT(STR(URI(factoids:)), "AREA_", STRUUID())) AS ?landmark)
        ?tmpLandmark a addr:Landmark; addr:isLandmarkType ltype:District ; skos:hiddenLabel ?hiddenLabel.
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)


def remove_temporary_landmarks_and_transfert_triples(graphdb_url:str, repository_name:str, named_graph_uri:str, query_prefixes:str):
    """
    Suppression de landmarks temporaires et transfert de tous ses triplets vers son landmark associé (celui tel que landmark skos:exactMatch landmark tempoaire)
    """
    query = query_prefixes + f"""
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


def add_missing_changes_and_events_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes):
    """
    Ajouter des éléments comme les changements (et événéments associés) manquants pour les repères
    """

    query = query_prefixes + f"""
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

def add_missing_changes_and_events_for_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes):
    """
    Ajouter des éléments comme les changements (et événéments associés) manquants pour les relations entre repères
    """

    query = query_prefixes + f"""
        INSERT {{
            GRAPH ?g {{
                ?change a addr:LandmarkRelationChange ; addr:isChangeType ?cgType ; addr:appliedTo ?landmark ; addr:dependsOn ?event .
                ?event a addr:Event .
            }}
        }} WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            ?landmarkRelation a addr:LandmarkRelation .
            VALUES ?cgType {{ ctype:LandmarkRelationAppearance ctype:LandmarkRelationDisappearance }}
            MINUS {{?change addr:appliedTo ?landmarkRelation ; addr:isChangeType ?cgType . }}
            BIND(URI(CONCAT(STR(URI(factoids:)), "CG_", STRUUID())) AS ?change)
            BIND(URI(CONCAT(STR(URI(factoids:)), "EV_", STRUUID())) AS ?event)
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def add_missing_changes_and_events_for_attributes(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes):
    """
    Ajouter des éléments comme les changements (et événéments associés) manquants pour les attributs (et leurs versions)
    """

    query = query_prefixes + f"""
        INSERT {{
            GRAPH ?g {{
                ?change a addr:AttributeChange ; addr:isChangeType ?cgType ; ?predOnVersion ?version ; addr:appliedTo ?attribute ; addr:dependsOn ?event .
                ?event a addr:Event .
            }}
        }} WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            ?attribute a addr:Attribute ; addr:hasAttributeVersion ?version.
            VALUES (?cgType ?predOnVersion) {{
                (ctype:LandmarkRelationAppearance addr:makesEffective)
                (ctype:LandmarkRelationDisappearance addr:outdates)
                }}
            MINUS {{?change addr:appliedTo ?attribute ; ?predOnVersion ?version ; addr:isChangeType ?cgType . }}
            BIND(URI(CONCAT(STR(URI(factoids:)), "CG_", STRUUID())) AS ?change)
            BIND(URI(CONCAT(STR(URI(factoids:)), "EV_", STRUUID())) AS ?event)
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def add_missing_attributes_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes):
    """
    Ajout d'attributs manquants pour les repères à partir des propriétés de base (rdfs:label, geo:asWKT...)
    """

    query = query_prefixes + f"""
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

def add_attributes_version_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes):
    """
    Ajout des versions d'attributs
    """

    query = query_prefixes + f"""
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

def add_temporal_information_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes):
    """
    Ajout des informations temporelles appliquées au repère
    """

    query = query_prefixes + f"""
        DELETE {{
            ?landmark ?lmTimePred ?time .
        }}
        INSERT {{
            GRAPH ?g {{
                ?event addr:hasTime ?time
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

def add_provenances_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes):
    """
    Ajout des liens de provenance des repères vers ses versions d'attributs et les valeurs temporelles
    """

    query = query_prefixes + f"""
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


def update_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes):
    """
    Ajouter des éléments comme les changements, les événements, les attributs et leurs versions
    """

    add_missing_changes_and_events_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes)
    add_missing_attributes_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes)
    add_attributes_version_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes)
    add_missing_changes_and_events_for_attributes(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes)
    add_temporal_information_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes)
    add_provenances_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes)
    
def update_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes):
    """
    Ajouter des éléments comme les changements, les événements, les attributs et leurs versions
    """

    add_missing_changes_and_events_for_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes)

def add_missing_temporal_information(graphdb_url, repository_name, factoids_named_graph_uri, time_description:dict, query_prefixes):
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

    query = query_prefixes + f"""
        INSERT {{
            GRAPH ?g {{
                ?event ?tPred ?timeInstant .
                ?timeInstant a addr:CrispTimeInstant ; addr:timeStamp ?ts ; addr:timePrecision ?tp ; addr:timeCalendar ?tc .
            }}
        }}
        WHERE {{
            BIND({factoids_named_graph_uri.n3()} AS ?g)
            ?cg a addr:Change ; addr:isChangeType ?cgType ; addr:dependsOn ?event .
            MINUS {{?event addr:hasTime ?t }}
            VALUES (?ts ?tp ?tc ?tPred ?cgType) {{
                {values}
            }}
            BIND(URI(CONCAT(STR(URI(factoids:)), "TI_", STRUUID())) AS ?timeInstant)
        }}
    """

    gd.update_query(query, graphdb_url, repository_name)

if __name__ == "__main__" :
    vpa_file = "/home/CBernard2/Téléchargements/denominations-emprises-voies-actuelles.csv"
    vpc_file = "/home/CBernard2/Téléchargements/denominations-des-voies-caduques.csv"
    vdp_kg_file = "/home/CBernard2/Téléchargements/test.ttl"
    header, rows = fm.read_csv_file(vpa_file, has_header=True, delimiter=";")
    lang = "fr"
    namespace_prefixes = {"addr":Namespace("http://rdf.geohistoricaldata.org/def/address#"),
                      "atype":Namespace("http://rdf.geohistoricaldata.org/id/codes/address/attributeType/"),
                      "ltype":Namespace("http://rdf.geohistoricaldata.org/id/codes/address/landmarkType/"),
                      "lrtype":Namespace("http://rdf.geohistoricaldata.org/id/codes/address/landmarkRelationType/"),
                      "ctype":Namespace("http://rdf.geohistoricaldata.org/id/codes/address/changeType/"),
                      "facts":Namespace("http://rdf.geohistoricaldata.org/id/address/facts/"),
                      "factoids":Namespace("http://rdf.geohistoricaldata.org/id/address/factoids/"),
                      "time": Namespace("http://www.w3.org/2006/time#"),
                      "owl": Namespace("http://www.w3.org/2002/07/owl#"),
                      "prov": Namespace("http://www.w3.org/ns/prov#"),
                      "rico": Namespace("https://www.ica.org/standards/RiC/ontology#"),
                      "geo": Namespace("http://www.opengis.net/ont/geosparql#"),
                      "skos": Namespace("http://www.w3.org/2004/02/skos/core#"),
                      "rdf": Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
                      "rdfs": Namespace("http://www.w3.org/2000/01/rdf-schema#"),
                      "xsd": Namespace("http://www.w3.org/2001/XMLSchema#"),
                      "geofla": Namespace("http://data.ign.fr/def/geofla#"),
                      }

    # URIs pour accéder aux logiciels GraphDB et Ontotext-Refine
    graphdb_url = "http://localhost:7200"

    # Nom du répertoire où sont stockés et construits les triplets des factoïdes des données de la BAN
    vpt_repository_name = "factoids_ville_de_paris"
    factoids_named_graph_name = "factoids"
    permanent_named_graph_name = "permanent"

    vpta_time_description = {
        "start_time" : {"stamp":"2024-02-10T00:00:00Z","precision":"day","calendar":"gregorian"}
    }

    g = create_graph_of_current_thoroughfares(vpa_file, vpta_time_description, namespace_prefixes, lang)
    g += create_graph_of_former_thoroughfares(vpc_file, vpta_time_description, namespace_prefixes, lang)
    g.serialize(vdp_kg_file)
    gd.import_ttl_file_in_graphdb(graphdb_url, vpt_repository_name, vdp_kg_file, factoids_named_graph_name)
    clean_vdp_repository(graphdb_url, vpt_repository_name, vpta_time_description, factoids_named_graph_name, permanent_named_graph_name, namespace_prefixes)