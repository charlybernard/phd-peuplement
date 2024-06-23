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
# import wikidata as wd
import re

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

## Données de la BAN

def create_graph_from_ban(ban_file, namespace_prefixes:dict, lang:str):
    ban_pref, ban_ns = "ban", Namespace("https://adresse.data.gouv.fr/base-adresse-nationale/")

    ## Colonnes du fichier BAN
    hn_id_col, hn_number_col, hn_rep_col, hn_lon_col, hn_lat_col = "id", "numero", "rep", "lon", "lat"
    th_name_col, th_fantoir_col = "nom_voie",  "id_fantoir"
    cp_number_col = "code_postal"
    arrdt_name_col, arrdt_insee_col = "nom_commune", "code_insee"    

    content = fm.read_csv_file_as_dict(ban_file, id_col=hn_id_col, delimiter=";", encoding='utf-8-sig')
    g = Graph()
    gr.add_namespaces_to_graph(g, namespace_prefixes)
    g.bind(ban_pref, ban_ns)

    for value in content.values():  
        hn_id = value.get(hn_id_col)
        hn_label = value.get(hn_number_col) + value.get(hn_rep_col)
        hn_geom = "POINT (" + value.get(hn_lon_col) + " " + value.get(hn_lat_col) + ")"
        th_label = value.get(th_name_col)
        th_id = value.get(th_fantoir_col)
        cp_label = value.get(cp_number_col)
        arrdt_label = value.get(arrdt_name_col)
        arrdt_id = value.get(arrdt_insee_col)

        create_data_value_from_ban(g, ban_ns, hn_id, hn_label, hn_geom, th_id, th_label, cp_label, arrdt_id, arrdt_label, lang, namespace_prefixes)

    return g

def clean_repository_ban(graphdb_url, ban_repository_name, ban_time_description, factoids_named_graph_name, permanent_named_graph_name, namespace_prefixes, lang):
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

def create_data_value_from_ban(g, ban_ns, hn_id, hn_label, hn_geom, th_id, th_label, cp_label, arrdt_id, arrdt_label, lang, namespace_prefixes):
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

    gr.create_landmark(g, hn_uri, hn_label, None, ltype_ns["HouseNumber"], addr_ns)
    gr.create_landmark_geometry(g, hn_uri, hn_geom)
    gr.create_landmark(g, th_uri, th_label, lang, ltype_ns["Thoroughfare"], addr_ns)
    gr.create_landmark(g, cp_uri, cp_label, None, ltype_ns["PostalCodeArea"], addr_ns)
    gr.create_landmark(g, arrdt_uri, arrdt_label, lang, ltype_ns["District"], addr_ns)
    gr.create_landmark_insee(g, arrdt_uri, arrdt_id)

    # Création de l'adresse (avec les segments d'adresse)
    gr.create_landmark_relation(g, addr_seg_1_uri, hn_uri, [hn_uri], lrtype_ns["IsSimilarTo"], addr_ns, is_address_segment=True)
    gr.create_landmark_relation(g, addr_seg_2_uri, hn_uri, [th_uri], lrtype_ns["Along"], addr_ns, is_address_segment=True)
    gr.create_landmark_relation(g, addr_seg_3_uri, hn_uri, [cp_uri], lrtype_ns["Within"], addr_ns, is_address_segment=True)
    gr.create_landmark_relation(g, addr_seg_4_uri, hn_uri, [arrdt_uri], lrtype_ns["Within"], addr_ns, is_final_address_segment=True)
    gr.create_address(g, addr_uri, addr_label, lang, [addr_seg_1_uri, addr_seg_2_uri, addr_seg_3_uri, addr_seg_4_uri], hn_uri, addr_ns)

    # Ajout de labels alternatifs pour les landmarks
    add_other_labels_for_landmark(g, hn_uri, hn_label, "housenumber", None)
    add_other_labels_for_landmark(g, th_uri, th_label, "thoroughfare", lang)
    add_other_labels_for_landmark(g, cp_uri, cp_label, "housenumber", None)
    add_other_labels_for_landmark(g, arrdt_uri, arrdt_label, "area", lang)

    # Ajout des sources
    prov_uris = [prov_hn_uri, prov_th_uri, prov_arrdt_uri]
    for uri in prov_uris:
        gr.create_prov_entity(g, prov_hn_uri)
    uris = [hn_uri, cp_uri, addr_uri, addr_seg_1_uri, addr_seg_2_uri, addr_seg_3_uri, addr_seg_4_uri]
    for uri in uris:
        gr.add_provenance_to_resource(g, uri, prov_hn_uri)
    gr.add_provenance_to_resource(g, th_uri, prov_th_uri)
    gr.add_provenance_to_resource(g, arrdt_uri, prov_arrdt_uri)


## Données d'OSM

def create_graph_from_osm(osm_file, osm_hn_file, namespace_prefixes:dict, lang:str):
    osm_pref, osm_ns = "osm", Namespace("http://www.openstreetmap.org/")
    osm_rel_pref, osm_rel_ns = "osmRel", Namespace("http://www.openstreetmap.org/relation/")

    ## Colonnes du fichier OSM
    hn_id_col, hn_number_col, hn_geom_col = "houseNumberId", "houseNumberName", "houseNumberGeomWKT"
    th_id_col, th_name_col = "streetId",  "streetName"
    arrdt_id_col, arrdt_name_col, arrdt_insee_col = "arrdtId", "arrdtName", "arrdtInsee"    

    # Lecture des deux fichiers
    content = fm.read_csv_file_as_dict(osm_file, id_col=hn_id_col, delimiter=",", encoding='utf-8-sig')
    content_hn = fm.read_csv_file_as_dict(osm_hn_file, id_col=hn_id_col, delimiter=",", encoding='utf-8-sig')

    g = Graph()
    gr.add_namespaces_to_graph(g, namespace_prefixes)
    g.bind(osm_pref, osm_ns)
    g.bind(osm_rel_pref, osm_rel_ns)

    for value in content.values(): 
        hn_id = value.get(hn_id_col)
        try:
            hn_label = content_hn.get(hn_id).get(hn_number_col)
        except:
            hn_label = None

        try:
            hn_geom = content_hn.get(hn_id).get(hn_geom_col)
        except:
            hn_geom = None

        th_label = value.get(th_name_col)
        th_id = value.get(th_id_col)
        arrdt_id = value.get(arrdt_id_col)
        arrdt_label = value.get(arrdt_name_col)
        arrdt_insee = value.get(arrdt_insee_col)

        create_data_value_from_osm(g, hn_id, hn_label, hn_geom, th_id, th_label, arrdt_id, arrdt_label, arrdt_insee, lang, namespace_prefixes)

    return g

def create_data_value_from_osm(g, hn_id, hn_label, hn_geom, th_id, th_label, arrdt_id, arrdt_label, arrdt_insee, lang, namespace_prefixes):
    factoids_ns = namespace_prefixes["factoids"]
    addr_ns = namespace_prefixes["addr"]
    ltype_ns = namespace_prefixes["ltype"]
    lrtype_ns = namespace_prefixes["lrtype"]

    # URIs des entités géographiques de la BAN
    hn_uri = gr.generate_uri(factoids_ns, "HN")
    th_uri = gr.generate_uri(factoids_ns, "TH")
    arrdt_uri = gr.generate_uri(factoids_ns, "ARRDT")
    
    prov_hn_uri = URIRef(hn_id)
    prov_th_uri = URIRef(th_id)
    prov_arrdt_uri = URIRef(arrdt_id)

    # URIs pour les relations entre repères
    lm_1_uri = gr.generate_uri(factoids_ns, "LR")
    lm_2_uri = gr.generate_uri(factoids_ns, "LR")

    gr.create_landmark(g, hn_uri, hn_label, None, ltype_ns["HouseNumber"], addr_ns)
    gr.create_landmark_geometry(g, hn_uri, hn_geom)
    gr.create_landmark(g, th_uri, th_label, lang, ltype_ns["Thoroughfare"], addr_ns)
    gr.create_landmark(g, arrdt_uri, arrdt_label, lang, ltype_ns["District"], addr_ns)
    gr.create_landmark_insee(g, arrdt_uri, arrdt_insee)

    # Création de l'adresse (avec les segments d'adresse)
    gr.create_landmark_relation(g, lm_1_uri, hn_uri, [hn_uri], lrtype_ns["Along"], addr_ns)
    gr.create_landmark_relation(g, lm_2_uri, hn_uri, [arrdt_uri], lrtype_ns["Within"], addr_ns)

    # Ajout de labels alternatifs pour les landmarks
    add_other_labels_for_landmark(g, hn_uri, hn_label, "housenumber", None)
    add_other_labels_for_landmark(g, th_uri, th_label, "thoroughfare", lang)
    add_other_labels_for_landmark(g, arrdt_uri, arrdt_label, "area", lang)

    # Ajout des sources
    prov_uris = [prov_hn_uri, prov_th_uri, prov_arrdt_uri]
    for uri in prov_uris:
        gr.create_prov_entity(g, prov_hn_uri)

    gr.add_provenance_to_resource(g, hn_uri, prov_hn_uri)
    gr.add_provenance_to_resource(g, th_uri, prov_th_uri)
    gr.add_provenance_to_resource(g, arrdt_uri, prov_arrdt_uri)
    gr.add_provenance_to_resource(g, lm_1_uri, prov_th_uri)
    gr.add_provenance_to_resource(g, lm_2_uri, prov_arrdt_uri)

def clean_repository_osm(graphdb_url, ban_repository_name, ban_time_description, factoids_named_graph_name, permanent_named_graph_name, namespace_prefixes, lang):
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
    vdp_source_uri = namespace_prefixes["facts"]["Source_OSM"]
    source_label = "OpenStreetMap"
    source_lang = "mul"
    create_source_resource(graphdb_url, ban_repository_name, vdp_source_uri, source_label, None, source_lang, namespace_prefixes["facts"], permanent_named_graph_uri, query_prefixes)
    link_provenances_with_source(graphdb_url, ban_repository_name, vdp_source_uri, permanent_named_graph_uri, query_prefixes)

## Données de la ville de Paris

def create_graph_from_ville_paris_caduques(vpc_file, source_time_description, namespace_prefixes:dict, lang:str):
    vpc_pref, vpc_ns = "vdpc", Namespace("https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/denominations-des-voies-caduques/records/")

    # Colonnes du fichier
    id_col = "Identifiant"
    name_col = "Dénomination complète minuscule"
    start_time_col = "Date de l'arrêté"
    end_time_col = "Date de caducité"
    arrdt_col = "Arrondissement"
    district_col = "Quartier"
    
    vpc_content = fm.read_csv_file_as_dict(vpc_file, id_col=id_col, delimiter=";", encoding='utf-8-sig')
    g = Graph()
    gr.add_namespaces_to_graph(g, namespace_prefixes)
    g.bind(vpc_pref, vpc_ns)

    for value in vpc_content.values():
        th_id = value.get(id_col)
        th_label = value.get(name_col)
        th_start_time = value.get(start_time_col)
        th_end_time = value.get(end_time_col)
        th_arrdt_names = sp.split_cell_content(value.get(arrdt_col), sep=",")
        th_district_names = sp.split_cell_content(value.get(district_col), sep=",")

        create_data_value_from_ville_paris_caduques(g, th_id, th_label, th_start_time, th_end_time, th_arrdt_names, th_district_names, source_time_description, vpc_ns, namespace_prefixes, lang)

    return g

def create_data_value_from_ville_paris_caduques(g:Graph, id:str, label:str, start_time_stamp:str, end_time_stamp:str, arrdt_labels:list[str], district_labels:list[str], source_time_description, vpa_ns:Namespace, namespace_prefixes:dict, lang:str):
    """
    `source_time_description` : dictionnaire décrivant les dates de début et de fin de validité de la source
    `source_time_description = {"start_time":{"stamp":..., "precision":..., "calendar":...}, "end_time":{} }`
    """

    factoids_ns = namespace_prefixes["factoids"]
    addr_ns = namespace_prefixes["addr"]
    ltype_ns = namespace_prefixes["ltype"]
    lrtype_ns = namespace_prefixes["lrtype"]

    # URI de la voie, création de cette dernière et ajout de labels alternatifs
    th_uri = gr.generate_uri(factoids_ns, "TH")
    gr.create_landmark(g, th_uri, label, lang, ltype_ns["Thoroughfare"], addr_ns)
    add_other_labels_for_landmark(g, th_uri, label, "thoroughfare", lang)

    # Ajout d'informations temporelles pour les voies
    start_time_stamp, start_time_calendar, start_time_precision, start_time_pred = get_thoroughfare_start_time(start_time_stamp, source_time_description)
    end_time_stamp, end_time_precision, end_time_calendar, end_time_pred = get_former_thoroughfare_end_time(end_time_stamp, source_time_description)
    add_related_time_to_landmark(g, th_uri, start_time_stamp, start_time_calendar, start_time_precision, start_time_pred, namespace_prefixes)
    add_related_time_to_landmark(g, th_uri, end_time_stamp, end_time_calendar, end_time_precision, end_time_pred, namespace_prefixes)

    # Création de la provenance
    th_prov_uri = vpa_ns[id]
    gr.create_prov_entity(g, th_prov_uri)
    gr.add_provenance_to_resource(g, th_uri, th_prov_uri)

    # Liste des zones à créer (arrondissement et quartier), chaque élément est une liste dont la 1re valeur est la label et la seconde est son type
    areas = [[re.sub("^0", "", x.replace("01e", "01er")) + " arrondissement de Paris", "District"] for x in arrdt_labels] + [[x, "District"] for x in district_labels]
    for area in areas:
        area_label, area_type = area
        area_uri = gr.generate_uri(factoids_ns, "LM") # URI de la zone
        lr_uri = gr.generate_uri(factoids_ns, "LR") # URI de la relation entre la voie et la zone
        gr.create_landmark(g, area_uri, area_label, lang, ltype_ns[area_type], addr_ns)
        gr.create_landmark_relation(g, lr_uri, th_uri, [area_uri], lrtype_ns["Within"], addr_ns)
        add_other_labels_for_landmark(g, area_uri, area_label, "area", lang)
        
        # Ajout des provenances
        gr.add_provenance_to_resource(g, area_uri, th_prov_uri)
        gr.add_provenance_to_resource(g, lr_uri, th_prov_uri)


def create_graph_from_ville_paris_actuelles(vpa_file, source_time_description, namespace_prefixes:dict, lang:str):
    vpa_pref, vpa_ns = "vdpa", Namespace("https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/denominations-emprises-voies-actuelles/records/")
    
    # Colonnes du fichier
    id_col = "Identifiant"
    name_col = "Dénomination complète minuscule"
    start_time_col = "Date de l'arrété"
    arrdt_col = "Arrondissement"
    district_col = "Quartier"
    geom_col = "geo_shape"

    content = fm.read_csv_file_as_dict(vpa_file, id_col=id_col, delimiter=";", encoding='utf-8-sig')
    g = Graph()
    gr.add_namespaces_to_graph(g, namespace_prefixes)
    g.bind(vpa_pref, vpa_ns)

    source_time_description = tp.get_valid_time_description(source_time_description)

    for value in content.values():
        th_id = value.get(id_col)
        th_label = value.get(name_col)
        th_geom = value.get(geom_col)
        th_start_time = value.get(start_time_col)
        th_arrdt_labels = sp.split_cell_content(value.get(arrdt_col), sep=",")
        th_district_labels = sp.split_cell_content(value.get(district_col), sep=",")

        create_data_value_from_ville_paris_actuelles(g, th_id, th_label, th_geom, th_start_time, th_arrdt_labels, th_district_labels, source_time_description, vpa_ns, namespace_prefixes, lang)

    return g

def create_data_value_from_ville_paris_actuelles(g:Graph, id:str, label:str, geom:str, start_time_stamp:str, arrdt_labels:list[str], district_labels:list[str], source_time_description, vpa_ns:Namespace, namespace_prefixes:dict, lang:str):
    """
    `source_time_description` : dictionnaire décrivant les dates de début et de fin de validité de la source
    `source_time_description = {"start_time":{"stamp":..., "precision":..., "calendar":...}, "end_time":{} }`
    """

    factoids_ns = namespace_prefixes["factoids"]
    addr_ns = namespace_prefixes["addr"]
    ltype_ns = namespace_prefixes["ltype"]
    lrtype_ns = namespace_prefixes["lrtype"]

    # Conversion de la geométrie (qui est un geojson en string) vers un WKT
    geom = gp.from_geojson_to_wkt(json.loads(geom))

    # URI de la voie, création de cette dernière, ajout d'une géométrie et de labels alternatifs
    th_uri = gr.generate_uri(factoids_ns, "TH")
    gr.create_landmark(g, th_uri, label, lang, ltype_ns["Thoroughfare"], addr_ns)
    gr.create_landmark_geometry(g, th_uri, geom)
    add_other_labels_for_landmark(g, th_uri, label, "thoroughfare", lang)

    # Ajout d'informations temporelles
    start_time_stamp, start_time_calendar, start_time_precision, start_time_pred = get_thoroughfare_start_time(start_time_stamp, source_time_description)
    end_time_stamp, end_time_precision, end_time_calendar = tp.get_time_instant_elements(source_time_description.get("end_time"))
    end_time_pred = "hasEarliestEndTime"

    add_related_time_to_landmark(g, th_uri, start_time_stamp, start_time_calendar, start_time_precision, start_time_pred, namespace_prefixes)
    add_related_time_to_landmark(g, th_uri, end_time_stamp, end_time_calendar, end_time_precision, end_time_pred, namespace_prefixes)

    # Création de la provenance
    th_prov_uri = vpa_ns[id]
    gr.create_prov_entity(g, th_prov_uri)
    gr.add_provenance_to_resource(g, th_uri, th_prov_uri)

    # Liste des zones à créer (arrondissement et quartier), chaque élément est une liste dont la 1re valeur est la label et la seconde est son type
    areas = [[re.sub("^0", "", x.replace("01e", "01er")) + " arrondissement de Paris", "District"] for x in arrdt_labels] + [[x, "District"] for x in district_labels]
    for area in areas:
        area_label, area_type = area
        area_uri = gr.generate_uri(factoids_ns, "LM") # URI de la zone
        lr_uri = gr.generate_uri(factoids_ns, "LR") # URI de la relation entre la voie et la zone
        gr.create_landmark(g, area_uri, area_label, lang, ltype_ns[area_type], addr_ns)
        gr.create_landmark_relation(g, lr_uri, th_uri, [area_uri], lrtype_ns["Within"], addr_ns)
        add_other_labels_for_landmark(g, area_uri, area_label, "area", lang)
        
        # Ajout des provenances
        gr.add_provenance_to_resource(g, area_uri, th_prov_uri)
        gr.add_provenance_to_resource(g, lr_uri, th_prov_uri)  

## Données de Wikidata

def get_paris_landmarks_from_wikidata(out_csv_file):
    """
    Obtention des voies de Paris et des communes de l'ancien département de la Seine
    """

    query = """
        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
        PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#> 
        PREFIX source: <http://rdf.geohistoricaldata.org/id/address/sources/wikidata/> 
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX pq: <http://www.wikidata.org/prop/qualifier/>
        PREFIX ps: <http://www.wikidata.org/prop/statement/>
        PREFIX p: <http://www.wikidata.org/prop/>
        PREFIX pqv: <http://www.wikidata.org/prop/qualifier/value/>
        PREFIX wb: <http://wikiba.se/ontology#>
        PREFIX time: <http://www.w3.org/2006/time#>

        SELECT DISTINCT ?landmarkId ?landmarkType ?nomOff ?dateStartStamp ?dateStartPrec ?dateStartCal ?dateEndStamp ?dateEndPrec ?dateEndCal ?statement ?statementType
        WHERE {
        {
            ?landmarkId p:P361 [ps:P361 wd:Q16024163].
            BIND("Thoroughfare" AS ?landmarkType)
        }UNION{
            ?landmarkId p:P361 [ps:P361 wd:Q107311481].
            BIND("Thoroughfare" AS ?landmarkType)
        }UNION{
            ?landmarkId p:P31 [ps:P31 wd:Q252916].
            BIND("District" AS ?landmarkType)
        }UNION{
            ?landmarkId p:P31 [ps:P31 wd:Q702842]; p:P131 [ps:P131 wd:Q90].
            BIND("District" AS ?landmarkType)
        }UNION{
            ?landmarkId p:P31 [ps:P31 wd:Q484170]; p:P131 [ps:P131 wd:Q1142326].
            BIND("City" AS ?landmarkType)
        }
        {
            ?landmarkId p:P1448 ?nomOffSt.
            ?nomOffSt ps:P1448 ?nomOff.
            BIND(?nomOffSt AS ?statement)
            BIND(wb:Statement AS ?statementType)
            OPTIONAL {?nomOffSt pq:P580 ?dateStartStamp; pqv:P580 [wb:timePrecision ?dateStartPrecRaw; wb:timeCalendarModel ?dateStartCal]}
            OPTIONAL {?nomOffSt pq:P582 ?dateEndStamp; pqv:P582 [wb:timePrecision ?dateEndPrecRaw; wb:timeCalendarModel ?dateEndCal]}
        }UNION{
            ?landmarkId rdfs:label ?nomOff.
            FILTER (LANG(?nomOff) = "fr")
            MINUS {?landmarkId p:P1448 ?nomOffSt}
            BIND(?landmarkId AS ?statement)
            BIND(wb:Item AS ?statementType)
        }
        BIND(IF(?dateStartPrecRaw = 11, time:unitDay, 
                    IF(?dateStartPrecRaw = 10, time:unitMonth,
                    IF(?dateStartPrecRaw = 9, time:unitYear,
                        IF(?dateStartPrecRaw = 8, time:unitDecade,
                            IF(?dateStartPrecRaw = 7, time:unitCentury,
                                IF(?dateStartPrecRaw = 6, time:unitMillenium, ?x
                                )))))) AS ?dateStartPrec)
        BIND(IF(?dateEndPrecRaw = 11, time:unitDay, 
                    IF(?dateEndPrecRaw = 10, time:unitMonth,
                    IF(?dateEndPrecRaw = 9, time:unitYear,
                        IF(?dateEndPrecRaw = 8, time:unitDecade,
                            IF(?dateEndPrecRaw = 7, time:unitCentury,
                                IF(?dateEndPrecRaw = 6, time:unitMillenium, ?x
                                )))))) AS ?dateEndPrec)
        }
    """

    query = wd.save_select_query_as_csv_file(query, out_csv_file)


def get_paris_locations_from_wikidata(out_csv_file):
    """
    Obtenir la localisation des données (voies et zones) de Paris depuis Wikidata"""

    query = """
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX pq: <http://www.wikidata.org/prop/qualifier/>
    PREFIX ps: <http://www.wikidata.org/prop/statement/>
    PREFIX p: <http://www.wikidata.org/prop/>
    PREFIX pqv: <http://www.wikidata.org/prop/qualifier/value/>
    PREFIX wb: <http://wikiba.se/ontology#>
    PREFIX time: <http://www.w3.org/2006/time#>

    SELECT DISTINCT ?locatumId ?relatumId ?landmarkRelationType ?dateStartStamp ?dateStartPrec ?dateStartCal ?dateEndStamp ?dateEndPrec ?dateEndCal ?statement WHERE {
    {
        ?locatumId p:P361 [ps:P361 wd:Q16024163].
    }UNION{
        ?locatumId p:P361 [ps:P361 wd:Q107311481].
    }UNION{
        ?locatumId p:P31 [ps:P31 wd:Q252916].
    }UNION{
        ?locatumId p:P31 [ps:P31 wd:Q702842]; p:P131 [ps:P131 wd:Q90].
    }UNION{
        ?locatumId p:P31 [ps:P31 wd:Q484170]; p:P131 [ps:P131 wd:Q1142326].
    }
    ?locatumId p:P131 ?statement.
    ?statement ps:P131 ?relatumId. 
    OPTIONAL {?statement pq:P580 ?dateStartStamp; pqv:P580 [wb:timePrecision ?dateStartPrecRaw; wb:timeCalendarModel ?dateStartCal]}
    OPTIONAL {?statement pq:P582 ?dateEndStamp; pqv:P582 [wb:timePrecision ?dateEndPrecRaw; wb:timeCalendarModel ?dateEndCal]}
    BIND("Within" AS ?landmarkRelationType)
    BIND(IF(?dateStartPrecRaw = 11, time:unitDay, 
            IF(?dateStartPrecRaw = 10, time:unitMonth,
                IF(?dateStartPrecRaw = 9, time:unitYear,
                    IF(?dateStartPrecRaw = 8, time:unitDecade,
                    IF(?dateStartPrecRaw = 7, time:unitCentury,
                        IF(?dateStartPrecRaw = 6, time:unitMillenium, ?x
                            )))))) AS ?dateStartPrec)
    BIND(IF(?dateEndPrecRaw = 11, time:unitDay, 
            IF(?dateEndPrecRaw = 10, time:unitMonth,
                IF(?dateEndPrecRaw = 9, time:unitYear,
                    IF(?dateEndPrecRaw = 8, time:unitDecade,
                    IF(?dateEndPrecRaw = 7, time:unitCentury,
                        IF(?dateEndPrecRaw = 6, time:unitMillenium, ?x
                            )))))) AS ?dateEndPrec)
    }
    """
    
    query = wd.save_select_query_as_csv_file(query, out_csv_file)

## Faire appel aux endpoint de Wikidata pour sélectionner des données
def get_data_from_wikidata(wdp_land_csv_file, wdp_loc_csv_file):
    """
    Obtenir les fichiers CSV pour les données provenant de Wikidata
    """
    get_paris_landmarks_from_wikidata(wdp_land_csv_file)
    get_paris_locations_from_wikidata(wdp_loc_csv_file)

def create_graph_from_wikidata_paris(wdp_land_file, wdp_loc_file, namespace_prefixes, lang):
    wd_pref, wd_ns = "wd", Namespace("http://www.wikidata.org/entity/")
    wds_pref, wds_ns = "wds", Namespace("http://www.wikidata.org/entity/statement/")
    wb_pref, wb_ns = "wb", Namespace("http://wikiba.se/ontology#")

    ## Colonnes du fichier Wikidata
    lm_id_col, lm_type_col, lm_label_col =  "landmarkId", "landmarkType", "nomOff"
    prov_id_col, prov_id_type_col = "statement", "statementType"
    lr_type_col = "landmarkRelationType"
    locatum_id_col, relatum_id_col = "locatumId","relatumId"
    start_time_stamp_col, start_time_prec_col, start_time_cal_col = "dateStartStamp", "dateStartPrec", "dateStartCal"
    end_time_stamp_col, end_time_prec_col, end_time_cal_col = "dateEndStamp", "dateEndPrec", "dateEndCal"

    # Lecture des deux fichiers
    content_lm = fm.read_csv_file_as_dict(wdp_land_file, id_col=lm_id_col, delimiter=",", encoding='utf-8-sig')
    content_lr = fm.read_csv_file_as_dict(wdp_loc_file, delimiter=",", encoding='utf-8-sig')

    g = Graph()
    gr.add_namespaces_to_graph(g, namespace_prefixes)
    g.bind(wd_pref, wd_ns)
    g.bind(wds_pref, wds_ns)
    g.bind(wb_pref, wb_ns)

    # Création des landmarks
    for value in content_lm.values(): 
        lm_id = value.get(lm_id_col)
        lm_label = value.get(lm_label_col)
        lm_type = value.get(lm_type_col)
        lm_prov_id = value.get(prov_id_col)
        lm_prov_id_type = value.get(prov_id_type_col)
        start_time_stamp = tp.get_literal_time_stamp(value.get(start_time_stamp_col)) if value.get(start_time_stamp_col) != "" else None
        start_time_prec = gr.get_valid_uri(value.get(start_time_prec_col))
        start_time_cal = gr.get_valid_uri(value.get(start_time_cal_col))
        start_time = [start_time_stamp, start_time_prec, start_time_cal]
        end_time_stamp = tp.get_literal_time_stamp(value.get(end_time_stamp_col)) if value.get(end_time_stamp_col) != "" else None
        end_time_prec = gr.get_valid_uri(value.get(end_time_prec_col))
        end_time_cal = gr.get_valid_uri(value.get(end_time_cal_col))
        end_time = [end_time_stamp, end_time_prec, end_time_cal]

        create_data_value_from_wikidata_landmark(g, lm_id, lm_label, lm_type, lm_prov_id, lm_prov_id_type, start_time, end_time, lang, namespace_prefixes, wb_ns)

    # Création des relations entre landmarks
    for value in content_lr.values(): 
        lr_type = value.get(lr_type_col)
        lr_prov_id = value.get(prov_id_col)
        locatum_id = value.get(locatum_id_col)
        relatum_id = value.get(relatum_id_col)

        create_data_value_from_wikidata_landmark_relation(g, lr_type, locatum_id, relatum_id, lr_prov_id, namespace_prefixes, wb_ns)

    return g

def create_data_value_from_wikidata_landmark(g, lm_id, lm_label, lm_type, lm_prov_id, lm_prov_id_type, start_time:list, end_time:list, lang, namespace_prefixes, wikibase_namespace):
    factoids_ns = namespace_prefixes["factoids"]
    addr_ns = namespace_prefixes["addr"]
    ltype_ns = namespace_prefixes["ltype"]

    # URIs du repère
    lm_uri = gr.generate_uri(factoids_ns, "LM")
    wd_lm_uri = URIRef(lm_id)
    g.add((wd_lm_uri, RDF.type, wikibase_namespace["Item"])) # Indiquer que `wd_lm_uri` est une entité Wikibase

    # Création de la provenance
    lm_prov_uri = URIRef(lm_prov_id)
    lm_prov_type_uri = URIRef(lm_prov_id_type)
    gr.create_prov_entity(g, lm_prov_uri)
    g.add((lm_prov_uri, RDF.type, lm_prov_type_uri))

    # Création du repère
    gr.create_landmark(g, lm_uri, lm_label, lang, ltype_ns[lm_type], addr_ns)
    gr.add_provenance_to_resource(g, lm_uri, lm_prov_uri)
    g.add((lm_uri, SKOS.closeMatch, wd_lm_uri)) # On indique que le landmark est proche (skos:closeMatch) de sa ressource sur Wikidata

    # Ajout de labels alternatifs pour les repères
    lm_types = {"Thoroughfare":"thoroughfare", "District":"area", "City":"area"}
    add_other_labels_for_landmark(g, lm_uri, lm_label, lm_types.get(lm_type), lang)

    # Ajout d'informations temporelles
    if None not in start_time:
        start_time_stamp, start_time_calendar, start_time_precision = start_time
        start_time_stamp = tp.get_literal_time_stamp(start_time_stamp)
        start_time_pred = "hasStartTime"
        add_related_time_to_landmark(g, lm_uri, start_time_stamp, start_time_calendar, start_time_precision, start_time_pred, namespace_prefixes)
    if None not in end_time:
        end_time_stamp, end_time_precision, end_time_calendar = end_time
        end_time_stamp = tp.get_literal_time_stamp(end_time_stamp)
        end_time_pred = "hasEndTime"
        add_related_time_to_landmark(g, lm_uri, end_time_stamp, end_time_calendar, end_time_precision, end_time_pred, namespace_prefixes)

def create_data_value_from_wikidata_landmark_relation(g, lr_type, locatum_id, relatum_id, lr_prov_id, namespace_prefixes, wikibase_namespace):
    factoids_ns = namespace_prefixes["factoids"]
    addr_ns = namespace_prefixes["addr"]
    lrtype_ns = namespace_prefixes["lrtype"]

    # URIs de la relation entre repères
    lr_uri = gr.generate_uri(factoids_ns, "LR")
    locatum_uri = URIRef(locatum_id)
    relatum_uri = URIRef(relatum_id)

    # Création de la provenance
    lr_prov_uri = URIRef(lr_prov_id)
    gr.create_prov_entity(g, lr_prov_uri)
    g.add((lr_prov_uri, RDF.type, wikibase_namespace["Statement"]))  # Indiquer que `lr_prov_uri` est un statement Wikibase

    # Création de la relation entre repères
    gr.create_landmark_relation(g, lr_uri, locatum_uri, [relatum_uri], lrtype_ns[lr_type], addr_ns)
    gr.add_provenance_to_resource(g, lr_uri, lr_prov_uri)


def create_landmark_relations_for_wikidata_paris(graphdb_url:str, repository_name:str, factoids_named_graph_uri:URIRef, query_prefixes:str):
    query = query_prefixes + f"""
    DELETE {{
        ?wdLr a addr:LandmarkRelation ; addr:isLandmarkRelationType ?lrType ; addr:locatum ?wdLoc ; addr:relatum ?wdRel ; prov:wasDerivedFrom ?prov.
    }}
    INSERT {{
        GRAPH ?g {{
            ?lr a addr:LandmarkRelation ; addr:isLandmarkRelationType ?lrType ; addr:locatum ?loc ; addr:relatum ?rel ; prov:wasDerivedFrom ?prov.
        }}
    }}
    WHERE {{
        BIND({factoids_named_graph_uri.n3()} AS ?g)
        ?wdLr a addr:LandmarkRelation ; addr:isLandmarkRelationType ?lrType ; addr:locatum ?wdLoc ; addr:relatum ?wdRel ; prov:wasDerivedFrom ?prov.
        OPTIONAL {{
        ?l skos:closeMatch ?wdLoc .
    	?r skos:closeMatch ?wdRel .
    	BIND(URI(CONCAT(STR(URI(factoids:)), "LR_", STRUUID())) AS ?lmRel)
        }}
        BIND(BOUND(?l) && BOUND(?r) AS ?exist)
        BIND(IF(?exist, ?lmRel, ?x) AS ?lr)
        BIND(IF(?exist, ?l, ?x) AS ?loc)
        BIND(IF(?exist, ?r, ?x) AS ?rel)
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)


def clean_repository_wikidata_paris(graphdb_url:str, repository_name:str, source_time_description:dict, factoids_named_graph_name:str, permanent_named_graph_name:str, namespace_prefixes:dict, lang:str):
    query_prefixes = gd.get_query_prefixes_from_namespaces(namespace_prefixes)
    factoids_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, factoids_named_graph_name))
    permanent_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, permanent_named_graph_name))

    create_landmark_relations_for_wikidata_paris(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes)

    # Ajout d'éléments manquants comme les changements, événements, attributs, versions d'attributs
    update_landmarks(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes)
    update_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri, query_prefixes)

    # source_time_description = tp.get_valid_time_description(source_time_description)
    # add_missing_temporal_information(graphdb_url, repository_name, factoids_named_graph_uri, source_time_description, query_prefixes)

    # Transférer toutes les descriptions de provenance vers le graphe nommé permanent
    msp.transfert_immutable_triples(graphdb_url, repository_name, factoids_named_graph_uri, permanent_named_graph_uri)

    # L'URI ci-dessous définit la source liée à la ville de Paris
    vdp_source_uri = namespace_prefixes["facts"]["Source_WD"]
    source_label = "Wikidata"
    source_lang = "mul"
    create_source_resource(graphdb_url, repository_name, vdp_source_uri, source_label, None, source_lang, namespace_prefixes["facts"], permanent_named_graph_uri, query_prefixes)
    link_provenances_with_source(graphdb_url, repository_name, vdp_source_uri, permanent_named_graph_uri, query_prefixes)

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


def add_related_time_to_landmark(g:Graph, lm_uri:URIRef, time_stamp:Literal, time_calendar:URIRef, time_precision:URIRef, time_predicate:str, namespace_prefixes:dict):
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
    g.add((lm_uri, namespace_prefixes["addr"][time_predicate], time_uri))

def clean_repository_ville_paris(graphdb_url:str, repository_name:str, source_time_description:dict, factoids_named_graph_name:str, permanent_named_graph_name:str, namespace_prefixes:dict, lang:str):
    query_prefixes = gd.get_query_prefixes_from_namespaces(namespace_prefixes)
    factoids_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, factoids_named_graph_name))
    permanent_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, permanent_named_graph_name))

    # Fusion des repères similaires
    landmark_type = namespace_prefixes["ltype"]["District"]
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

def add_other_labels_for_landmark(g:Graph, lm_uri:URIRef, lm_label_value:str, lm_label_type:str, lm_label_lang):
    # Ajout de labels alternatif et caché
    alt_label, hidden_label = sp.normalize_and_simplify_name_version(lm_label_value, lm_label_type, lm_label_lang)
    alt_label_lit = Literal(alt_label, lang=lm_label_lang)
    hidden_label_lit = Literal(hidden_label, lang=lm_label_lang)
    g.add((lm_uri, SKOS.altLabel, alt_label_lit))
    g.add((lm_uri, SKOS.hiddenLabel, hidden_label_lit))

if __name__ == "__main__" :
    vpa_file = "/Users/charlybernard/Documents/Projects/phd-peuplement/sources/data/denominations-emprises-voies-actuelles.csv"
    vpc_file = "/Users/charlybernard/Documents/Projects/phd-peuplement/sources/data/denominations-des-voies-caduques.csv"
    ban_file = "/Users/charlybernard/Documents/Projects/phd-peuplement/sources/data/ban_adresses.csv"
    osm_file = "/Users/charlybernard/Documents/Projects/phd-peuplement/sources/data/osm_adresses.csv"
    osm_hn_file = "/Users/charlybernard/Documents/Projects/phd-peuplement/sources/data/osm_hn_adresses.csv"
    wdp_land_file = "/Users/charlybernard/Documents/Projects/phd-peuplement/sources/data/wd_paris_landmarks.csv"
    wdp_loc_file = "/Users/charlybernard/Documents/Projects/phd-peuplement/sources/data/wd_paris_locations.csv"
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
    osm_repository_name = "factoids_osm"
    wd_repository_name = "factoids_wikidata"
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
    # clean_repository_ville_paris(graphdb_url, vpt_repository_name, vpta_time_description, factoids_named_graph_name, permanent_named_graph_name, namespace_prefixes, lang)


    # ban_time_description = {
    #     "start_time" : {"stamp":"2023-01-01T00:00:00Z","precision":"day","calendar":"gregorian"}
    # }
    
    # g = create_graph_from_ban(ban_file, namespace_prefixes, lang)
    # g.serialize(vdp_kg_file)
    # gd.reinitialize_repository(graphdb_url, ban_repository_name, local_config_file, ruleset_name="rdfsplus-optimized", disable_same_as=True, allow_removal=True)
    # gd.load_ontologies(graphdb_url, ban_repository_name, [ont_file], ontology_named_graph_name)
    # gd.import_ttl_file_in_graphdb(graphdb_url, ban_repository_name, vdp_kg_file, factoids_named_graph_name)
    # clean_repository_ban(graphdb_url, ban_repository_name, ban_time_description, factoids_named_graph_name, permanent_named_graph_name, namespace_prefixes, lang)

    # osm_time_description = {
    #     "start_time" : {"stamp":"2024-06-01T00:00:00Z","precision":"day","calendar":"gregorian"}
    # }
    
    # g = create_graph_from_osm(osm_file, osm_hn_file, namespace_prefixes, lang)
    # g.serialize(vdp_kg_file)
    # gd.reinitialize_repository(graphdb_url, osm_repository_name, local_config_file, ruleset_name="rdfsplus-optimized", disable_same_as=True, allow_removal=True)
    # gd.load_ontologies(graphdb_url, osm_repository_name, [ont_file], ontology_named_graph_name)
    # gd.import_ttl_file_in_graphdb(graphdb_url, osm_repository_name, vdp_kg_file, factoids_named_graph_name)
    # clean_repository_osm(graphdb_url, osm_repository_name, osm_time_description, factoids_named_graph_name, permanent_named_graph_name, namespace_prefixes, lang)

    wd_time_description = {}
    gd.reinitialize_repository(graphdb_url, wd_repository_name, local_config_file, ruleset_name="rdfsplus-optimized", disable_same_as=True, allow_removal=True)
    gd.load_ontologies(graphdb_url, wd_repository_name, [ont_file], ontology_named_graph_name)
    # get_data_from_wikidata(wdp_land_file, wdp_loc_file)
    g = create_graph_from_wikidata_paris(wdp_land_file, wdp_loc_file, namespace_prefixes, lang)
    g.serialize(vdp_kg_file)
    gd.import_ttl_file_in_graphdb(graphdb_url, wd_repository_name, vdp_kg_file, factoids_named_graph_name)
    clean_repository_wikidata_paris(graphdb_url, wd_repository_name, wd_time_description, factoids_named_graph_name, permanent_named_graph_name, namespace_prefixes, lang)