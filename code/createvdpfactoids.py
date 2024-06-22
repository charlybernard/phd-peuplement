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

## Colonnes des fichiers CSV

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

def get_ban_column_indices(header):
    hn_id_col = "id"
    hn_number_col = "numero"
    hn_rep_col = "rep"
    th_name_col = "nom_voie"
    th_fantoir_col = "id_fantoir"
    cp_number_col = "code_postal"
    arrdt_name_col = "nom_commune"
    arrdt_insee_col = "code_insee"
    hn_lon_col = "lon"
    hn_lat_col = "lat"

    hn_id_col_index = header.index(hn_id_col)
    hn_number_col_index = header.index(hn_number_col)
    hn_rep_col_index = header.index(hn_rep_col)
    th_name_col_index = header.index(th_name_col)
    th_fantoir_col_index = header.index(th_fantoir_col)
    cp_number_col_index = header.index(cp_number_col)
    arrdt_name_col_index = header.index(arrdt_name_col)
    arrdt_insee_col_index = header.index(arrdt_insee_col)
    hn_lon_col_index = header.index(hn_lon_col)
    hn_lat_col_index = header.index(hn_lat_col)

    col_indices = {"hn_id": hn_id_col_index ,"hn_number":hn_number_col_index,"hn_rep":hn_rep_col_index,"hn_lon":hn_lon_col_index,"hn_lat":hn_lat_col_index,
                   "th_name":th_name_col_index,"th_fantoir":th_fantoir_col_index,
                   "cp_number":cp_number_col_index,
                   "arrdt_name":arrdt_name_col_index, "arrdt_insee":arrdt_insee_col_index}

    return col_indices

## Création des sources

def create_source_resource(graphdb_url, repository_name, source_uri:URIRef, source_label:str, publisher_label:str, lang:str, namespace:Namespace, named_graph_uri:URIRef, query_prefixes:str):
    """
    Création de la source relative aux données de la ville de Paris
    """

    source_label_lit = Literal(source_label, lang=lang)

    query = query_prefixes + f"""
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
        query = query_prefixes + f"""
        INSERT DATA {{
            GRAPH {named_graph_uri.n3()} {{
                {source_uri.n3()} rico:hasPublisher {publisher_uri.n3()} .
                {publisher_uri.n3()} a rico:CorporateBody;
                    rdfs:label {publisher_label_lit.n3()}.    
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

def create_graph_from_ban(ban_file, namespace_prefixes:dict, lang:str):
    ban_pref, ban_ns = "ban", Namespace("https://adresse.data.gouv.fr/base-adresse-nationale/")
    
    header, rows = fm.read_csv_file(ban_file, has_header=True, delimiter=";", encoding='utf-8-sig')
    col_indices = get_ban_column_indices(header)
    g = Graph()
    gr.add_namespaces_to_graph(g, namespace_prefixes)
    g.bind(ban_pref, ban_ns)

    for row in rows:  
        hn_id = row[col_indices.get("hn_id")]
        hn_label = row[col_indices.get("hn_number")] + row[col_indices.get("hn_rep")]
        hn_geom = "POINT (" + row[col_indices.get("hn_lon")] + " " + row[col_indices.get("hn_lat")] + ")"
        th_label = row[col_indices.get("th_name")]
        th_id = row[col_indices.get("th_fantoir")]
        cp_label = row[col_indices.get("cp_number")]
        arrdt_label = row[col_indices.get("arrdt_name")]
        arrdt_id = row[col_indices.get("arrdt_insee")]

        create_ban_data_line(g, ban_ns, hn_id, hn_label, hn_geom, th_id, th_label, cp_label, arrdt_id, arrdt_label, lang, namespace_prefixes)

    return g

def clean_ban_repository(graphdb_url, ban_repository_name, ban_time_description, factoids_named_graph_name, permanent_named_graph_name, namespace_prefixes, lang):
    query_prefixes = gd.get_query_prefixes_from_namespaces(namespace_prefixes)
    factoids_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, ban_repository_name, factoids_named_graph_name))
    permanent_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, ban_repository_name, permanent_named_graph_name))

    ltype_ns = namespace_prefixes["ltype"]

    ## Détection des arrondissements et quartiers qui ont un hiddenLabel similaire
    landmark_type = ltype_ns["District"]
    detect_similar_landmarks_with_hidden_label(graphdb_url, ban_repository_name, landmark_type, factoids_named_graph_uri, query_prefixes)

    ## Détection des codes postaux qui ont un hiddenLabel similaire
    landmark_type = ltype_ns["PostalCodeArea"]
    detect_similar_landmarks_with_hidden_label(graphdb_url, ban_repository_name, landmark_type, factoids_named_graph_uri, query_prefixes)

    ## Détection des voies qui ont un hiddenLabel similaire
    landmark_type = ltype_ns["Thoroughfare"]
    detect_similar_landmarks_with_hidden_label(graphdb_url, ban_repository_name, landmark_type, factoids_named_graph_uri, query_prefixes)

    # Fusion des repères similaires
    remove_temporary_landmarks_and_transfert_triples(graphdb_url, ban_repository_name, factoids_named_graph_uri, query_prefixes)

    # Ajout d'éléments manquants comme les changements, événements, attributs, versions d'attributs
    update_landmarks(graphdb_url, ban_repository_name, factoids_named_graph_uri, query_prefixes)
    update_landmark_relations(graphdb_url, ban_repository_name, factoids_named_graph_uri, query_prefixes)

    source_time_description = tp.get_valid_time_description(ban_time_description)
    add_missing_temporal_information(graphdb_url, ban_repository_name, factoids_named_graph_uri, source_time_description, query_prefixes)

    # Transférer toutes les descriptions de provenance vers le graphe nommé permanent
    msp.transfert_immutable_triples(graphdb_url, ban_repository_name, factoids_named_graph_uri, permanent_named_graph_uri)

    # L'URI ci-dessous définit la source liée à la ville de Paris
    vdp_source_uri = namespace_prefixes["facts"]["Source_BAN"]
    source_label = "Base Adresse Nationale"
    publisher_label = "DINUM / ANCT / IGN"
    create_source_resource(graphdb_url, ban_repository_name, vdp_source_uri, source_label, publisher_label, lang, namespace_prefixes["facts"], permanent_named_graph_uri, query_prefixes)
    link_provenances_with_source(graphdb_url, ban_repository_name, vdp_source_uri, permanent_named_graph_uri, query_prefixes)


def create_ban_data_line(g, ban_ns, hn_id, hn_label, hn_geom, th_id, th_label, cp_label, arrdt_id, arrdt_label, lang, namespace_prefixes):
    factoids_ns = namespace_prefixes["factoids"]
    addr_ns = namespace_prefixes["addr"]
    ltype_ns = namespace_prefixes["ltype"]
    lrtype_ns = namespace_prefixes["lrtype"]

    # URIs des entités géographiques de la BAN
    hn_uri = gr.generate_uri(factoids_ns, "HN")
    th_uri = gr.generate_uri(factoids_ns, "TH")
    cp_uri = gr.generate_uri(factoids_ns, "CP")
    arrdt_uri = gr.generate_uri(factoids_ns, "ARRDT")
    
    prov_hn_uri = ban_ns[hn_id]
    prov_th_uri = ban_ns[th_id]
    prov_arrdt_uri = ban_ns[arrdt_id]

    # URIs pour l'adresse et ses segments
    addr_uri = gr.generate_uri(factoids_ns, "ADDR")
    addr_seg_1_uri = gr.generate_uri(factoids_ns, "AS")
    addr_seg_2_uri = gr.generate_uri(factoids_ns, "AS")
    addr_seg_3_uri = gr.generate_uri(factoids_ns, "AS")
    addr_seg_4_uri = gr.generate_uri(factoids_ns, "AS")

    addr_label = f"{hn_label} {th_label}, {cp_label} {arrdt_label}"

    gr.create_landmark(g, hn_uri, hn_label, None, "HouseNumber", addr_ns, ltype_ns)
    gr.create_landmark_geometry(g, hn_uri, hn_geom)
    gr.create_landmark(g, th_uri, th_label, lang, "Thoroughfare", addr_ns, ltype_ns)
    gr.create_landmark(g, cp_uri, cp_label, None, "PostalCodeArea", addr_ns, ltype_ns)
    gr.create_landmark(g, arrdt_uri, arrdt_label, lang, "District", addr_ns, ltype_ns)
    gr.create_landmark_insee(g, arrdt_uri, arrdt_id)

    # Création de l'adresse (avec les segments d'adresse)
    gr.create_landmark_relation(g, addr_seg_1_uri, hn_uri, [hn_uri], "IsSimilarTo", addr_ns, lrtype_ns, is_address_segment=True)
    gr.create_landmark_relation(g, addr_seg_2_uri, hn_uri, [th_uri], "Along", addr_ns, lrtype_ns, is_address_segment=True)
    gr.create_landmark_relation(g, addr_seg_3_uri, hn_uri, [cp_uri], "Within", addr_ns, lrtype_ns, is_address_segment=True)
    gr.create_landmark_relation(g, addr_seg_4_uri, hn_uri, [arrdt_uri], "Within", addr_ns, lrtype_ns, is_final_address_segment=True)
    gr.create_address(g, addr_uri, addr_label, lang, [addr_seg_1_uri, addr_seg_2_uri, addr_seg_3_uri, addr_seg_4_uri], hn_uri, addr_ns)

    # Ajout de labels alternatifs pour les landmarks
    add_other_labels_for_landmark(g, hn_uri, hn_label, "housenumber", None)
    add_other_labels_for_landmark(g, th_uri, th_label, "thoroughfare", lang)
    add_other_labels_for_landmark(g, cp_uri, cp_label, "housenumber", None)
    add_other_labels_for_landmark(g, arrdt_uri, arrdt_label, "area", lang)

    # Ajout des sources
    gr.create_prov_entity(g, prov_hn_uri)
    uris = [hn_uri, cp_uri, addr_uri, addr_seg_1_uri, addr_seg_2_uri, addr_seg_3_uri, addr_seg_4_uri]
    for uri in uris:
        gr.add_provenance_to_resource(g, uri, prov_hn_uri)
    gr.add_provenance_to_resource(g, th_uri, prov_th_uri)
    gr.add_provenance_to_resource(g, arrdt_uri, prov_arrdt_uri)

def create_graph_from_ville_paris_caduques(vpc_file, source_time_description, namespace_prefixes:dict, lang:str):
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
        th_arrdts = sp.split_cell_content(row[col_indices.get("arrdt")], sep=",")
        th_districts = sp.split_cell_content(row[col_indices.get("district")], sep=",")

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

def create_graph_from_ville_paris_actuelles(vpa_file, source_time_description, namespace_prefixes:dict, lang:str):
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
        th_arrdts = sp.split_cell_content(row[col_indices.get("arrdt")], sep=",")
        th_districts = sp.split_cell_content(row[col_indices.get("district")], sep=",")

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

def get_thoroughfare_start_time(start_time_stamp, source_time_description):
    time_elements = tp.get_gregorian_date_from_timestamp(start_time_stamp)
    if None in time_elements:
        start_time_stamp, start_time_precision, start_time_calendar = tp.get_time_instant_elements(source_time_description.get("start_time"))
        start_time_pred = "hasLatestStartTime"
    else:
        start_time_stamp, start_time_precision, start_time_calendar = time_elements
        start_time_pred = "hasStartTime"
        
    return start_time_stamp, start_time_calendar, start_time_precision, start_time_pred

def get_former_thoroughfare_end_time(start_time_stamp, source_time_description):
    time_elements = tp.get_gregorian_date_from_timestamp(start_time_stamp)
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
    alt_label_lit = Literal(alt_label, lang=lm_label_lang)
    hidden_label_lit = Literal(hidden_label, lang=lm_label_lang)
    g.add((lm_uri, SKOS.altLabel, alt_label_lit))
    g.add((lm_uri, SKOS.hiddenLabel, hidden_label_lit))

def clean_vdp_repository(graphdb_url:str, repository_name:str, source_time_description:dict, factoids_named_graph_name:str, permanent_named_graph_name:str, namespace_prefixes:dict, lang:str):
    query_prefixes = gd.get_query_prefixes_from_namespaces(namespace_prefixes)
    factoids_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, factoids_named_graph_name))
    permanent_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, permanent_named_graph_name))

    # Fusion des repères similaires
    landmark_type = namespace_prefixes["addr"]["District"]
    detect_similar_landmarks_with_hidden_label(graphdb_url, repository_name, landmark_type, factoids_named_graph_uri, query_prefixes)
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
    source_label = "dénomination des voies de Paris (actuelles et caduques)"
    publisher_label = "Département de la Topographie et de la Documentation Foncière de la Ville de Paris"
    create_source_resource(graphdb_url, repository_name, vdp_source_uri, source_label, publisher_label, lang, namespace_prefixes["facts"], permanent_named_graph_uri, query_prefixes)
    link_provenances_with_source(graphdb_url, repository_name, vdp_source_uri, permanent_named_graph_uri, query_prefixes)


def detect_similar_landmarks_with_hidden_label(graphdb_url, repository_name, landmark_type:URIRef, factoids_named_graph_uri, query_prefixes):
    # Détection de repères similaires sur le seul critère de similarité du hiddenlabel (il faut qu'ils aient le même type)
    query = query_prefixes + f"""
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

# def detect_similar_housenumbers(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes):
#     # Détection de similarité entre housenumbers : il faut qu'ils aient la même valeur et aient une relation entre repère de type Along avec la même voie.
#     query = query_prefixes + f"""
#     INSERT {{
#         GRAPH ?g {{
#             ?landmark skos:exactMatch ?tmpLandmark.
#         }}
#     }}
#     WHERE
#     {{
#         BIND({factoids_named_graph_uri.n3()} AS ?g)
#         {{
#             SELECT DISTINCT ?label ?district WHERE {{
#                 GRAPH ?g {{
#                     ?tmpLandmark a addr:Landmark; addr:isLandmarkType ltype:Thoroughfare; skos:hiddenLabel ?label.
#                     ?addrSeg a addr:AddressSegment; addr:relatum ?tmpLandmark; addr:nextStep [a addr:AddressSegment; addr:relatum ?tmpDistrict].
#                     ?tmpDistrict a addr:Landmark; addr:isLandmarkType ltype:District.
#                     ?district skos:exactMatch ?tmpDistrict.
#                 }}
#             }}
#         }}
#         BIND(URI(CONCAT(STR(URI(factoids:)), "BAN_LM_", STRUUID())) AS ?landmark)

#         GRAPH ?g {{
#             ?tmpLandmark a addr:Landmark; addr:isLandmarkType ltype:Thoroughfare; skos:hiddenLabel ?label.
#                     ?addrSeg a addr:AddressSegment; addr:relatum ?tmpLandmark; addr:nextStep [a addr:AddressSegment; addr:relatum ?tmpDistrict].
#                     ?tmpDistrict a addr:Landmark; addr:isLandmarkType ltype:District.
#                     ?district skos:exactMatch ?tmpDistrict.
#         }}
#     }}
#     """

#     gd.update_query(query, graphdb_url, repository_name)

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

if __name__ == "__main__" :
    vpa_file = "/Users/charlybernard/Documents/Projects/phd-peuplement/sources/data/denominations-emprises-voies-actuelles.csv"
    vpc_file = "/Users/charlybernard/Documents/Projects/phd-peuplement/sources/data/denominations-des-voies-caduques.csv"
    ban_file = "/Users/charlybernard/Documents/Projects/phd-peuplement/sources/data/ban_adresses.csv"
    local_config_file = "/Users/charlybernard/Documents/Projects/phd-peuplement/sources/tmp_files/loc_file.ttl"
    vdp_kg_file = "/Users/charlybernard/Documents/Projects/phd-peuplement/sources/tmp_files/test.ttl"
    ont_file = "/Users/charlybernard/Documents/Projects/phd-peuplement/sources/ontology.ttl"
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
    ban_repository_name = "factoids_ban"
    factoids_named_graph_name = "factoids"
    permanent_named_graph_name = "permanent"
    ontology_named_graph_name = "ontology"

    # vpta_time_description = {
    #     "start_time" : {"stamp":"2024-02-10T00:00:00Z","precision":"day","calendar":"gregorian"}
    # }
    # gd.reinitialize_repository(graphdb_url, vpt_repository_name, local_config_file, ruleset_name="rdfsplus-optimized", disable_same_as=True, allow_removal=True)
    # gd.load_ontologies(graphdb_url, vpt_repository_name, [ont_file], ontology_named_graph_name)
    # g = create_graph_from_ville_paris_actuelles(vpa_file, vpta_time_description, namespace_prefixes, lang)
    # g += create_graph_from_ville_paris_caduques(vpc_file, vpta_time_description, namespace_prefixes, lang)
    # g.serialize(vdp_kg_file)
    # gd.import_ttl_file_in_graphdb(graphdb_url, vpt_repository_name, vdp_kg_file, factoids_named_graph_name)
    # clean_vdp_repository(graphdb_url, vpt_repository_name, vpta_time_description, factoids_named_graph_name, permanent_named_graph_name, namespace_prefixes, lang)


    ban_time_description = {
        "start_time" : {"stamp":"2023-01-01T00:00:00Z","precision":"day","calendar":"gregorian"}
    }
    
    g = create_graph_from_ban(ban_file, namespace_prefixes, lang)
    g.serialize(vdp_kg_file)
    gd.reinitialize_repository(graphdb_url, ban_repository_name, local_config_file, ruleset_name="rdfsplus-optimized", disable_same_as=True, allow_removal=True)
    gd.load_ontologies(graphdb_url, ban_repository_name, [ont_file], ontology_named_graph_name)
    gd.import_ttl_file_in_graphdb(graphdb_url, ban_repository_name, vdp_kg_file, factoids_named_graph_name)
    clean_ban_repository(graphdb_url, ban_repository_name, ban_time_description, factoids_named_graph_name, permanent_named_graph_name, namespace_prefixes, lang)