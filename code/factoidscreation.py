import csv
import json
import geomprocessing as gp
import filemanagement as fm
import strprocessing as sp
import multisourcesprocessing as msp
import wikidata as wd
import graphdb as gd
import graphrdf as gr
from rdflib import Graph, RDFS, Literal, URIRef, Namespace, XSD

# Ville de Paris (Nomenclature des voies de la ville de Paris)
## Cette section présente des fonctions pour créer des factoïdes concernant les données de la ville de Paris

def create_source_ville_paris(graphdb_url, repository_name, source_uri:URIRef, named_graph_uri:URIRef):
    """
    Création de la source relative aux données de la ville de Paris
    """

    query = f"""
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#> 
    PREFIX facts: <http://rdf.geohistoricaldata.org/id/address/facts/>
    PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>

    INSERT DATA {{
        GRAPH {named_graph_uri.n3()} {{
            {source_uri.n3()} a rico:Record;
                rdfs:label "dénomination des voies de Paris (actuelles et caduques)"@fr;
                rico:hasPublisher facts:DirTopoDocFoncVP .
            facts:DirTopoDocFoncVP a rico:CorporateBody;
                rdfs:label "Département de la Topographie et de la Documentation Foncière de la Ville de Paris"@fr.    
        }}
    }}
    """
    
    gd.update_query(query, graphdb_url, repository_name)

## Le fichier de la nomenclature des voies actuelles de Paris comporte une colonne décrivant la géométrie des voies en geojson, la remplacer par du WKT
## Le fichier `vpta_csv_file` comporte une colonne donnant la géométrie de la voie (donnée ici par la variable `vpta_csv_file_geom_col_name`). 
## Toutefois, les géométries sont représentées en geojson mais il est nécessaire de les avoir en WKT. La fonction ci-dessous permet de faire la conversion en enregistrant la nouvelle version sous un nouveau fichier.
def get_csv_file_with_wkt_geom(csv_file_raw, csv_file, geom_column, delimiter=","):
    """
    Obtention d'une nouvelle version d'un fichier csv en convertissant une des colonnes (`geom_column`) en géométrie WKT si celle-ci est une géométrie geojson
    Le fichier de départ est `csv_file_raw` et la nouvelle version est `csv_file`.
    """
    file1 = open(csv_file_raw)
    file2 = open(csv_file, "w")
    csvreader1 = csv.reader(file1, delimiter=delimiter)
    csvreader2 = csv.writer(file2, delimiter=delimiter)

    header = next(csvreader1)
    csvreader2.writerow(header)
    geom_index = header.index(geom_column)

    for row in csvreader1:
        str_geom = row[geom_index]
        geom = json.loads(str_geom)
        wkt_geom = gp.from_geojson_to_wkt(geom)
        row[geom_index] = wkt_geom
        csvreader2.writerow(row)

    file1.close()
    file2.close()


def create_factoid_process_ville_paris(graphdb_url, repository_name, namespace_prefixes, tmp_folder,
                                       ontorefine_url, ontorefine_cmd,
                                       ont_file, ontology_named_graph_name,
                                       factoids_named_graph_name, permanent_named_graph_name,
                                       vpta_csv_file, vpta_mod_csv_file,
                                       vpta_csv_file_delimiter, vpta_csv_file_geom_col_name, vptc_csv_file,
                                       vpta_mapping_file, vptc_mapping_file,
                                       vpta_kg_file, vptc_kg_file, 
                                       vpta_time_description={}):
    """
    Fonction pour faire l'ensemble des processus relatifs à la création des factoïdes pour les données de la dénomination des voies de la ville de Paris
    """

    # Création d'un répertoire des factoïdes pour les données de la ville de Paris
    msp.create_factoid_repository(graphdb_url, repository_name, namespace_prefixes, tmp_folder, ont_file, ontology_named_graph_name, disable_same_as=False, clear_if_exists=True)

    # Récupération des URI des graphes nommés
    factoids_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, factoids_named_graph_name))
    permanent_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, permanent_named_graph_name))

    # Création d'une nouvelle version du fichier `vpta_csv_file` via `vpta_mod_csv_file` qui comporte des géométries WKT au lieu de geojson
    get_csv_file_with_wkt_geom(vpta_csv_file, vpta_mod_csv_file, vpta_csv_file_geom_col_name, vpta_csv_file_delimiter)

    # A partir des fichiers csv décrivant les voies de la ville de Paris, convertir en un graphe de connaissance selon le mapping défini
    msp.from_raw_to_data_to_graphdb(graphdb_url, ontorefine_url, ontorefine_cmd, repository_name, factoids_named_graph_name, vpta_mod_csv_file, vpta_mapping_file, vpta_kg_file)

    # Ajouter des approximations sur les événéments liés aux voies actuelles
    msp.remove_time_instant_without_timestamp(graphdb_url, repository_name) # Suppression des instants qui n'ont aucun timeStamp (instants sans date)
    msp.create_time_resources_for_current_sources(graphdb_url, repository_name, factoids_named_graph_uri, vpta_time_description)

    # Puis import du graphe dans le répertoire dont le nom est `repository_name` et dans le graphe nommé donné par `named_graph_name`
    msp.from_raw_to_data_to_graphdb(graphdb_url, ontorefine_url, ontorefine_cmd, repository_name, factoids_named_graph_name, vptc_csv_file, vptc_mapping_file, vptc_kg_file)

    # Suppression des instants qui n'ont aucun timeStamp (instants sans date)
    msp.remove_time_instant_without_timestamp(graphdb_url, repository_name)
    
    # L'URI ci-dessous définit la source liée à la ville de Paris
    vdp_source_uri = URIRef("http://rdf.geohistoricaldata.org/id/address/facts/Source_VDP")
    create_source_ville_paris(graphdb_url, repository_name, vdp_source_uri, permanent_named_graph_uri)

    # Transfert de triplets non modifiables vers le graphe nommé permanent
    msp.transfert_immutable_triples(graphdb_url, repository_name, factoids_named_graph_uri, permanent_named_graph_uri)

    # # Ajout de liens entre les ressources de type repère et la source
    # msp.add_factoids_resources_links(graphdb_url, repository_name, factoids_named_graph_uri)

# Base Adresse Nationale (BAN)
## Cette section présente des fonctions pour créer des factoïdes concernant les données de la Base Adresse Nationale

def create_source_ban(graphdb_url, repository_name, source_uri:URIRef, named_graph_uri:URIRef):
    """
    Création de la source relative aux données de la BAN
    """

    query = f"""
        PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#> 
        PREFIX facts: <http://rdf.geohistoricaldata.org/id/address/facts/>
        PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>

        INSERT DATA {{
            GRAPH {named_graph_uri.n3()} {{
                {source_uri.n3()} a rico:Record;
                    rdfs:label "Base Adresse Nationale"@fr;
                    rico:hasPublisher facts:DINUM_ANCT_IGN .
                facts:DINUM_ANCT_IGN a rico:CorporateBody;
                    rdfs:label "DINUM / ANCT / IGN"@fr.
            }}
        }}
        """
    
    gd.update_query(query, graphdb_url, repository_name)

# Détection des communes et arrondissements dupliqués et création d'une source centrale (?newLandmark) selon le code INSEE.
def clean_ban_graph(graphdb_url, repository_name, factoids_named_graph_uri, permanent_named_graph_uri):
    """
    Détection de repères décrits via plusieurs ressources et création d'une unique ressource pour chaque.
    """

    prefixes = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX prov: <http://www.w3.org/ns/prov#>
    PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>
    PREFIX geofla: <http://data.ign.fr/def/geofla#>
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX ltype: <http://rdf.geohistoricaldata.org/id/codes/address/landmarkType/>
    PREFIX bpa: <http://rdf.geohistoricaldata.org/id/address/sources/ban/>
    """

    label_var = "?label"
    norm_label_var = "?normLabel"
    norm_label_function = sp.get_lower_simplified_french_street_name_function(label_var)

    query1 = prefixes + f"""
    INSERT {{
        GRAPH ?g {{
            ?landmark skos:hiddenLabel {norm_label_var}.
        }}
    }}
    WHERE {{
        BIND({factoids_named_graph_uri.n3()} AS ?g)
        GRAPH ?g {{
            ?landmark a addr:Landmark; rdfs:label {label_var}.
            BIND(REPLACE({norm_label_function}, " ", "") AS {norm_label_var})
        }}
    }}
    """

    query2 = prefixes + f"""
    INSERT {{
        GRAPH ?g {{
            ?landmark skos:exactMatch ?tmpLandmark.
        }}
    }}
    WHERE
    {{
        BIND({factoids_named_graph_uri.n3()} AS ?g)
        {{
            SELECT DISTINCT ?insee {{
                GRAPH ?g {{
                    ?tmpLandmark a addr:Landmark; geofla:numInsee ?insee.
                }}
            }}
        }}
        BIND(URI(CONCAT(STR(URI(bpa:)), "BAN_LM_", STRUUID())) AS ?landmark)

        GRAPH ?g {{
            ?tmpLandmark a addr:Landmark; addr:isLandmarkType ?landmarkType; geofla:numInsee ?insee.
        }}
    }}
    """

    # Détection des doublons sur les codes postaux
    query3 = prefixes + f"""
    INSERT {{
        GRAPH ?g {{
            ?landmark skos:exactMatch ?tmpLandmark.
        }}
    }}
    WHERE
    {{
        BIND({factoids_named_graph_uri.n3()} AS ?g)
        {{
            SELECT DISTINCT ?postalCode {{
                GRAPH ?g {{
                    ?tmpLandmark a addr:Landmark; addr:isLandmarkType ltype:PostalCodeArea; rdfs:label ?postalCode.
                }}
            }}
        }}
        BIND(URI(CONCAT(STR(URI(bpa:)), "BAN_LM_", STRUUID())) AS ?landmark)

        GRAPH ?g {{
            ?tmpLandmark a addr:Landmark; addr:isLandmarkType ltype:PostalCodeArea; rdfs:label ?postalCode.
        }}
    }}
    """

    # Détection des doublons sur les voies (même nom et appartient à la même commune ou au même arrondissement)

    query4 = prefixes + f"""
    INSERT {{
        GRAPH ?g {{
            ?landmark skos:exactMatch ?tmpLandmark.
        }}
    }}
    WHERE
    {{
        BIND({factoids_named_graph_uri.n3()} AS ?g)
        {{
            SELECT DISTINCT ?label ?district WHERE {{
                GRAPH ?g {{
                    ?tmpLandmark a addr:Landmark; addr:isLandmarkType ltype:Thoroughfare; skos:hiddenLabel ?label.
                    ?addrSeg a addr:AddressSegment; addr:relatum ?tmpLandmark; addr:nextStep [a addr:AddressSegment; addr:relatum ?tmpDistrict].
                    ?tmpDistrict a addr:Landmark; addr:isLandmarkType ltype:District.
                    ?district skos:exactMatch ?tmpDistrict.
                }}
            }}
        }}
        BIND(URI(CONCAT(STR(URI(bpa:)), "BAN_LM_", STRUUID())) AS ?landmark)

        GRAPH ?g {{
            ?tmpLandmark a addr:Landmark; addr:isLandmarkType ltype:Thoroughfare; skos:hiddenLabel ?label.
                    ?addrSeg a addr:AddressSegment; addr:relatum ?tmpLandmark; addr:nextStep [a addr:AddressSegment; addr:relatum ?tmpDistrict].
                    ?tmpDistrict a addr:Landmark; addr:isLandmarkType ltype:District.
                    ?district skos:exactMatch ?tmpDistrict.
        }}
    }}
    """
    # Transfert des données des ressources temporaires vers les permanentes.
    query5 = prefixes + f"""
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
        BIND({factoids_named_graph_uri.n3()} AS ?g)
        GRAPH ?g {{
            ?landmark skos:exactMatch ?tmpLandmark.
        }}
    }}
    """

    queries = [query1, query2, query3, query4, query5]
    for query in queries:
        gd.update_query(query, graphdb_url, repository_name)

def create_factoid_process_ban(graphdb_url, repository_name, namespace_prefixes, tmp_folder,
                               ontorefine_url, ontorefine_cmd, ont_file, ontology_named_graph_name,
                               factoids_named_graph_name, permanent_named_graph_name,
                               ban_csv_file, ban_mapping_file, ban_kg_file,
                               ban_time_description={}):

    """
    Fonction pour faire l'ensemble des processus relatifs à la création des factoïdes pour les données de la BAN
    """

    # Création d'un répertoire des factoïdes pour les données de la BAN
    msp.create_factoid_repository(graphdb_url, repository_name, namespace_prefixes, tmp_folder, ont_file, ontology_named_graph_name, disable_same_as=False, clear_if_exists=True)

    # Récupération des URI des graphes nommés
    factoids_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, factoids_named_graph_name))
    permanent_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, permanent_named_graph_name))

    # A partir des fichiers csv décrivant les adresses de la BAN dans Paris, convertir en un graphe de connaissance selon le mapping défini
    # Puis import du graphe dans le répertoire dont le nom est `repository_name` et dans le graphe nommé donné par `named_graph_name`
    msp.from_raw_to_data_to_graphdb(graphdb_url, ontorefine_url, ontorefine_cmd, repository_name, factoids_named_graph_name, ban_csv_file, ban_mapping_file, ban_kg_file)

    # Suppression des instants qui n'ont aucun timeStamp (instants sans date)
    msp.remove_time_instant_without_timestamp(graphdb_url, repository_name)

    # Nettoyer les données en fusionnant les doublons après l'import dans GraphDB
    clean_ban_graph(graphdb_url, repository_name, factoids_named_graph_uri, permanent_named_graph_uri)

    # Ajout d'éléments manquants (changements et événéments)
    msp.add_missing_elements_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri)
    msp.add_missing_elements_for_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri)

    # Ajouter des approximations sur les événéments qui n'ont pas de valeur temporelle
    msp.create_time_resources_for_current_sources(graphdb_url, repository_name, factoids_named_graph_uri, ban_time_description)

    # L'URI ci-dessous définit la source liée à la BAN
    ban_factoids_uri = URIRef("http://rdf.geohistoricaldata.org/id/address/facts/Source_BAN")
    create_source_ban(graphdb_url, repository_name, ban_factoids_uri, permanent_named_graph_uri)

    # Transfert de triplets non modifiables vers le graphe nommé permanent
    msp.transfert_immutable_triples(graphdb_url, repository_name, factoids_named_graph_uri, permanent_named_graph_uri)
   
    # Ajout de liens entre les ressources de type repère et la source
    msp.add_factoids_resources_links(graphdb_url, repository_name, factoids_named_graph_uri)


# Wikidata (voies et zones autour de Paris)
def create_source_wikidata(graphdb_url, repository_name, source_uri:URIRef, named_graph_uri:URIRef):
    """
    Création de la source relative aux données de Wikidata
    """

    query = f"""
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#> 
    PREFIX facts: <http://rdf.geohistoricaldata.org/id/address/facts/>
    PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>

    INSERT DATA {{
        GRAPH {named_graph_uri.n3()} {{
            {source_uri.n3()} a rico:Record;
                rdfs:label "Wikidata"@fr.
        }}
    }}
    """
    
    gd.update_query(query, graphdb_url, repository_name)

def clean_wikidata_graph(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, permanent_named_graph_uri:URIRef):
    prefixes = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX geofla: <http://data.ign.fr/def/geofla#>
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX time: <http://www.w3.org/2006/time#> 
    PREFIX ltype: <http://rdf.geohistoricaldata.org/id/codes/address/landmarkType/>
    PREFIX bpa: <http://rdf.geohistoricaldata.org/id/address/sources/ban/>
    PREFIX wb: <http://wikiba.se/ontology#>
    """

    query1 =  prefixes + f"""
    INSERT DATA{{
        GRAPH {permanent_named_graph_uri.n3()} {{
            wb:Statement a owl:Class.
            wb:Item a owl:Class.
        }}
    }}
    """

    queries = [query1]
    for query in queries:
        gd.update_query(query, graphdb_url, repository_name)


## Sélection des voies de Paris sur Wikidata via une requête de sélection
"""
Via une requête SPARQL de sélection, on récupère une liste de ressources à créér :
* pour chaque ressource décrivant une voie dans Paris, on créé autant de ressources qu'elle a de nom officiel. 
    * La place de la Nation ([wd:Q1573359](https://www.wikidata.org/entity/Q1573359)) a quatre noms officiels donc on aura 4 ressources.
    * Pour celles qui n'ont pas de nom officiel, on créé une seule ressource dont le nom est le label en français
* ces ressources créées seront liées à celle de Wikidata dont elle provient via `skos:closeMatch`
* chaque ressource créée suit la structure définie par l'ontologie
* le résultat de la requête est stocké dans un fichier csv qui sera converti en graphe de connaissance via Ontotext Refine et un fichier de mapping 
"""

def get_paris_thoroughfares_from_wikidata(out_csv_file):
   query = """
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
   SELECT ?landmarkQid ?landmarkId ?landmarkType ?attributeNameVersionId ?nomOff ?dateStartStamp ?dateStartPrec ?dateStartCal ?dateEndStamp ?dateEndPrec ?dateEndCal ?statement ?statementType
   WHERE {
   BIND(CONCAT("LM_", STRUUID()) AS ?landmarkId)
   BIND(CONCAT("AN_", STRUUID()) AS ?attributeNameVersionId)
   {
      SELECT DISTINCT * WHERE {
        {?landmarkQid p:P361 [ps:P361 wd:Q16024163].}UNION{?landmarkQid p:P361 [ps:P361 wd:Q107311481].}
        {?landmarkQid p:P1448 ?nomOffSt.
        ?nomOffSt ps:P1448 ?nomOff.
        BIND(?nomOffSt AS ?statement)
        BIND(wb:Statement AS ?statementType)
        OPTIONAL {?nomOffSt pq:P580 ?dateStartStamp; pqv:P580 [wb:timePrecision ?dateStartPrecRaw; wb:timeCalendarModel ?dateStartCal]}
        OPTIONAL {?nomOffSt pq:P582 ?dateEndStamp; pqv:P582 [wb:timePrecision ?dateEndPrecRaw; wb:timeCalendarModel ?dateEndCal]}
        }UNION{
        ?landmarkQid rdfs:label ?nomOff.
        FILTER (LANG(?nomOff) = "fr")
        MINUS {?landmarkQid p:P1448 ?nomOffSt}
        BIND(?landmarkQid AS ?statement)
        BIND(wb:Item AS ?statementType)
        }
        BIND("Thoroughfare" AS ?landmarkType)
      }
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

   wd.save_select_query_as_csv_file(query, out_csv_file)

def get_areas_around_paris_from_wikidata(out_csv_file):
    """
    Sélection de zones autour de Paris (communes de l'ancien département de la Seine) et des quartiers / arrondissements de la capitale française"""
    
    query = """
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#> 
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

    SELECT ?landmarkQid ?landmarkId ?landmarkType ?attributeInseeCodeVersionId ?inseeCodeSt ?inseeCode ?inseeDateStartStamp ?inseeDateStartPrec ?inseeDateStartCal ?inseeDateEndStamp ?inseeDateEndPrec ?inseeDateEndCal ?attributeNameVersionId ?nomOff ?dateStartStamp ?dateStartPrec ?dateStartCal ?dateEndStamp ?dateEndPrec ?dateEndCal ?statement ?statementType 
    {
        {
        SELECT DISTINCT * WHERE {
        BIND(CONCAT("LM_", STRUUID()) AS ?landmarkId)
        BIND(CONCAT("ANV_", STRUUID()) AS ?attributeNameVersionId)
        {
            SELECT DISTINCT * WHERE {
            {?landmarkQid p:P31 [ps:P31 wd:Q252916].}UNION{?landmarkQid p:P31 [ps:P31 wd:Q702842]; p:P131 [ps:P131 wd:Q90].}UNION{?landmarkQid p:P31 [ps:P31 wd:Q484170]; p:P131 [ps:P131 wd:Q1142326].}
            {?landmarkQid p:P1448 ?nomOffSt.
            ?nomOffSt ps:P1448 ?nomOff.
            BIND(?nomOffSt AS ?statement)
            BIND(wb:Statement AS ?statementType)
            OPTIONAL {?nomOffSt pq:P580 ?dateStartStamp; pqv:P580 [wb:timePrecision ?dateStartPrecRaw; wb:timeCalendarModel ?dateStartCal]}
            OPTIONAL {?nomOffSt pq:P582 ?dateEndStamp; pqv:P582 [wb:timePrecision ?dateEndPrecRaw; wb:timeCalendarModel ?dateEndCal]}
            }UNION{
                ?landmarkQid rdfs:label ?nomOff.
                FILTER (LANG(?nomOff) = "fr")
                MINUS {?landmarkQid p:P1448 ?nomOffSt}
                BIND(?landmarkQid AS ?statement)
                BIND(wb:Item AS ?statementType)
            }
            ?landmarkQid p:P31 [ps:P31 ?wdLandmarkType].
            BIND(
                IF(?wdLandmarkType = wd:Q252916, "District",
                IF(?wdLandmarkType = wd:Q702842, "District",
                    IF(?wdLandmarkType = wd:Q484170, "City", ?x))) AS ?landmarkType)
            FILTER(BOUND(?landmarkType))
            }
        }
        OPTIONAL {?landmarkQid p:P374 ?inseeCodeSt.
                    ?inseeCodeSt ps:P374 ?inseeCode.
                    OPTIONAL {?inseeCodeSt pq:P580 ?inseeDateStartStamp; pqv:P580 [wb:timePrecision ?inseeDateStartPrecRaw; wb:timeCalendarModel ?inseeDateStartCal]}
                    OPTIONAL {?inseeCodeSt pq:P582 ?inseeDateEndStamp; pqv:P582 [wb:timePrecision ?inseeDateEndPrecRaw; wb:timeCalendarModel ?inseeDateEndCal]}
                }
        }
    }
    BIND(IF(BOUND(?inseeCodeSt), CONCAT("AIV_", STRUUID()), ?x) AS ?attributeInseeCodeVersionId)

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
    BIND(IF(?inseeDateStartPrecRaw = 11, time:unitDay, 
            IF(?inseeDateStartPrecRaw = 10, time:unitMonth,
                IF(?inseeDateStartPrecRaw = 9, time:unitYear,
                    IF(?inseeDateStartPrecRaw = 8, time:unitDecade,
                    IF(?inseeDateStartPrecRaw = 7, time:unitCentury,
                        IF(?inseeDateStartPrecRaw = 6, time:unitMillenium, ?x
                            )))))) AS ?inseeDateStartPrec)
    BIND(IF(?inseeDateEndPrecRaw = 11, time:unitDay, 
            IF(?inseeDateEndPrecRaw = 10, time:unitMonth,
                IF(?inseeDateEndPrecRaw = 9, time:unitYear,
                    IF(?inseeDateEndPrecRaw = 8, time:unitDecade,
                    IF(?inseeDateEndPrecRaw = 7, time:unitCentury,
                        IF(?inseeDateEndPrecRaw = 6, time:unitMillenium, ?x
                            )))))) AS ?inseeDateEndPrec)
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

    SELECT DISTINCT ?landmarkRelationId ?locatumQid ?relatumQid ?landmarkRelationType ?dateStartStamp ?dateStartPrec ?dateStartCal ?dateEndStamp ?dateEndPrec ?dateEndCal ?relatumQidSt WHERE {
    {?locatumQid p:P361 [ps:P361 wd:Q16024163].}UNION{?locatumQid p:P361 [ps:P361 wd:Q107311481].}UNION{?locatumQid p:P31 [ps:P31 wd:Q252916].}UNION{?locatumQid p:P31 [ps:P31 wd:Q702842]; p:P131 [ps:P131 wd:Q90].}UNION{?locatumQid p:P31 [ps:P31 wd:Q484170]; p:P131 [ps:P131 wd:Q1142326].}
    ?locatumQid p:P131 ?relatumQidSt.
    ?relatumQidSt ps:P131 ?relatumQid. 
    OPTIONAL {?relatumQidSt pq:P580 ?dateStartStamp; pqv:P580 [wb:timePrecision ?dateStartPrecRaw; wb:timeCalendarModel ?dateStartCal]}
    OPTIONAL {?relatumQidSt pq:P582 ?dateEndStamp; pqv:P582 [wb:timePrecision ?dateEndPrecRaw; wb:timeCalendarModel ?dateEndCal]}
    BIND("Within" AS ?landmarkRelationType)
    BIND(CONCAT("LR_", STRUUID()) AS ?landmarkRelationId)
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

## Création de relations entre repères (`LandmarkRelation`) provenant de wikidata

def transfert_landmark_relations_to_thoroughfares_wikidata(graphdb_url, repository_name, factoids_named_graph_uri:URIRef, tmp_named_graph_uri:URIRef):
    query = f"""
    PREFIX ctype: <http://rdf.geohistoricaldata.org/id/codes/address/changeType/>
    PREFIX lrtype: <http://rdf.geohistoricaldata.org/id/codes/address/landmarkRelationType/>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX prov: <http://www.w3.org/ns/prov#>
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX wikidata: <http://rdf.geohistoricaldata.org/id/address/sources/wikidata/>
    
    INSERT {{
        GRAPH ?gf {{
            ?landmarkRelation a addr:LandmarkRelation; addr:isLandmarkRelationType ?landmarkRelationType;
            addr:locatum ?cml; addr:relatum ?cmr; prov:wasDerivedFrom ?prov.
            ?lrChangeApp a addr:LandmarkRelationChange; addr:isChangeType ctype:LandmarkRelationAppearance; addr:appliedTo ?landmarkRelation; addr:dependsOn ?lrEventApp.
            ?lrChangeDis a addr:LandmarkRelationChange; addr:isChangeType ctype:LandmarkRelationDisappearance; addr:appliedTo ?landmarkRelation; addr:dependsOn ?lrEventDis.
            ?lrEventApp a addr:Event; addr:hasTime ?timeInstantApp.
            ?lrEventDis a addr:Event; addr:hasTime ?timeInstantDis.
            ?timeInstantApp a ?timeInstantAppType; addr:timeStamp ?timeInstantAppStamp; addr:timePrecision ?timeInstantAppPrec; addr:timeCalendar ?timeInstantAppCal.
            ?timeInstantDis a ?timeInstantDisType; addr:timeStamp ?timeInstantDisStamp; addr:timePrecision ?timeInstantDisPrec; addr:timeCalendar ?timeInstantDisCal.
        }}
    }}
    WHERE {{
        BIND({factoids_named_graph_uri.n3()} AS ?gf)
        BIND({tmp_named_graph_uri.n3()} AS ?gt)
        BIND(URI(CONCAT(STR(URI(wikidata:)), "LR_", STRUUID())) AS ?landmarkRelation)
        BIND(URI(CONCAT(STR(URI(wikidata:)), "CHA_", STRUUID())) AS ?lrChangeApp)
        BIND(URI(CONCAT(STR(URI(wikidata:)), "CHD_", STRUUID())) AS ?lrChangeDis)
        BIND(URI(CONCAT(STR(URI(wikidata:)), "EVA_", STRUUID())) AS ?lrEventApp)
        BIND(URI(CONCAT(STR(URI(wikidata:)), "EVD_", STRUUID())) AS ?lrEventDis)
        BIND(IF(BOUND(?timeInstantAppStamp), URI(CONCAT(STR(URI(wikidata:)), "TIA_", STRUUID())), ?x) AS ?timeInstantApp)
        BIND(IF(BOUND(?timeInstantDisStamp), URI(CONCAT(STR(URI(wikidata:)), "TID_", STRUUID())), ?x) AS ?timeInstantDis)
        {{
            SELECT DISTINCT * WHERE {{
                ?lr a addr:LandmarkRelation; addr:isLandmarkRelationType ?landmarkRelationType; addr:locatum ?l; addr:relatum ?r.
                ?changeApp a addr:Change; addr:isChangeType ctype:LandmarkRelationAppearance; addr:appliedTo ?lr; addr:dependsOn [a addr:Event; addr:hasTime ?timeInstantAppRaw].
                ?changeDis a addr:Change; addr:isChangeType ctype:LandmarkRelationDisappearance; addr:appliedTo ?lr; addr:dependsOn [a addr:Event; addr:hasTime ?timeInstantDisRaw].
                OPTIONAL {{
                    ?lr prov:wasDerivedFrom ?prov.
                }}
                OPTIONAL {{
                    GRAPH ?gt {{?timeInstantAppRaw a ?timeInstantAppType}}
                    ?timeInstantAppType rdfs:subClassOf* addr:TemporalEntity.
                    ?timeInstantAppRaw addr:timeStamp ?timeInstantAppStamp; addr:timePrecision ?timeInstantAppPrec; addr:timeCalendar ?timeInstantAppCal.
                    }}
                OPTIONAL {{
                    GRAPH ?gt {{?timeInstantDisRaw a ?timeInstantDisType}}
                    ?timeInstantDisType rdfs:subClassOf* addr:TemporalEntity.
                    ?timeInstantDisRaw addr:timeStamp ?timeInstantDisStamp; addr:timePrecision ?timeInstantDisPrec; addr:timeCalendar ?timeInstantDisCal.
                    }}
                ?cml skos:closeMatch ?l.
                ?cmr skos:closeMatch ?r.
            }}
        }}
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)
    gd.remove_named_graph_from_uri(tmp_named_graph_uri)

## Faire appel aux endpoint de Wikidata pour sélectionner des données
def get_data_from_wikidata(wdpt_csv_file, wdpa_csv_file, wdpl_csv_file):
    """
    Obtenir les fichiers CSV pour les données provenant de Wikidata
    """
    get_paris_thoroughfares_from_wikidata(wdpt_csv_file)
    get_areas_around_paris_from_wikidata(wdpa_csv_file)
    get_paris_locations_from_wikidata(wdpl_csv_file)

## Création des factoïdes venant de Wikidata
def create_factoid_process_wikidata(graphdb_url, repository_name, namespace_prefixes, tmp_folder,
                                    ontorefine_url, ontorefine_cmd, 
                                    ont_file, ontology_named_graph_name,
                                    factoids_named_graph_name, permanent_named_graph_name,
                                    wdpt_csv_file, wdpt_mapping_file, wdpt_kg_file,
                                    wdpa_csv_file, wdpa_mapping_file, wdpa_kg_file,
                                    wdpl_csv_file, wdpl_mapping_file, wdpl_kg_file):
    """
    Fonction pour faire l'ensemble des processus relatifs à la création des factoïdes pour les données de Wikidata
    """

    # Création d'un répertoire des factoïdes pour les données de Wikidata
    msp.create_factoid_repository(graphdb_url, repository_name, namespace_prefixes, tmp_folder, ont_file, ontology_named_graph_name, disable_same_as=False, clear_if_exists=True)

    # Récupération des URI des graphes nommés
    factoids_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, factoids_named_graph_name))
    permanent_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, permanent_named_graph_name))
    tmp_named_graph_name = "tmp"
    tmp_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, tmp_named_graph_name))

    # À partir des fichiers csv décrivant les repères liés à Paris (voies et zones), convertir en un graphe de connaissance selon le mapping défini
    # Puis import du graphe dans le répertoire dont le nom est `repository_name` et dans le graphe nommé donné par `named_graph_name`
    msp.from_raw_to_data_to_graphdb(graphdb_url, ontorefine_url, ontorefine_cmd, repository_name, factoids_named_graph_name, wdpt_csv_file, wdpt_mapping_file, wdpt_kg_file)
    msp.from_raw_to_data_to_graphdb(graphdb_url, ontorefine_url, ontorefine_cmd, repository_name, factoids_named_graph_name, wdpa_csv_file, wdpa_mapping_file, wdpa_kg_file)
    msp.from_raw_to_data_to_graphdb(graphdb_url, ontorefine_url, ontorefine_cmd, repository_name, tmp_named_graph_name, wdpl_csv_file, wdpl_mapping_file, wdpl_kg_file)

    # Transférer les relations spatiales entre les entités de Wikidata vers les entités créées
    transfert_landmark_relations_to_thoroughfares_wikidata(graphdb_url, repository_name, factoids_named_graph_uri, tmp_named_graph_uri)

    # Suppression des instants qui n'ont aucun timeStamp (instants sans date)
    msp.remove_time_instant_without_timestamp(graphdb_url, repository_name)

    # Nettoyage du graphe
    clean_wikidata_graph(graphdb_url, repository_name, factoids_named_graph_uri, permanent_named_graph_uri)

    # Ajouter des approximations sur les événéments qui n'ont pas de valeur temporelle
    msp.create_time_resources_for_current_sources(graphdb_url, repository_name, factoids_named_graph_uri)
    
    # Transfert de triplets non modifiables vers le graphe nommé permanent
    msp.transfert_immutable_triples(graphdb_url, repository_name, factoids_named_graph_uri, permanent_named_graph_uri)
    
    # L'URI ci-dessous définit la source liée à Wikidata
    wdpt_source_uri = URIRef("http://rdf.geohistoricaldata.org/id/address/facts/Source_WD")
    create_source_wikidata(graphdb_url, repository_name, wdpt_source_uri, permanent_named_graph_uri)

    # # Ajout de liens entre les ressources de type repère et la source
    # msp.add_factoids_resources_links(graphdb_url, repository_name, wdpt_source_uri, factoids_named_graph_uri)

# OpenStreetMap (OSM)
## Cette section présente des fonctions pour créer des factoïdes concernant les données de la ville de Paris

def create_source_osm(graphdb_url, repository_name, factoids_refactoids_uri:URIRef, facts_named_graph_uri:URIRef):
    """
    Création de la source relative aux données d'OSM
    """

    query = f"""
        PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#> 
        PREFIX facts: <http://rdf.geohistoricaldata.org/id/address/facts/>
        PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>

        INSERT DATA {{
            GRAPH {facts_named_graph_uri.n3()} {{
                {factoids_refactoids_uri.n3()} a rico:Record;
                    rdfs:label "OpenStreetMap"@mul.
            }}
        }}
        """
    
    gd.update_query(query, graphdb_url, repository_name)

## Détection des communes et arrondissements dupliqués et création d'une source centrale (?newLandmark) selon le code INSEE.
def clean_osm_graph(graphdb_url, repository_name, factoids_named_graph_uri, permanent_named_graph_uri):
    prefixes = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>
    PREFIX geofla: <http://data.ign.fr/def/geofla#>
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX ltype: <http://rdf.geohistoricaldata.org/id/codes/address/landmarkType/>
    """

    # Suppresion des numéros d'immeubles qui appartiennent à aucune voie
    query1 = prefixes + f"""
    DELETE {{
            ?hn ?p ?o.
            ?s ?p ?hn.
        }}
    WHERE {{
        ?hn a addr:Landmark; addr:isLandmarkType ltype:HouseNumber.
        MINUS {{?lr a addr:LandmarkRelation; addr:locatum ?hn; addr:relatum [a addr:Landmark; addr:isLandmarkType ?thoroughfare] }}
        {{?hn ?p ?o.}}UNION{{?s ?p ?hn.}}
    }}
    """
    
    queries = [query1]
    for query in queries:
        gd.update_query(query, graphdb_url, repository_name)

## Création des factoïdes venant d'OSM
def create_factoid_process_osm(graphdb_url, repository_name, namespace_prefixes, tmp_folder,
                               ontorefine_url, ontorefine_cmd, ont_file, ontology_named_graph_name,
                               factoids_named_graph_name, permanent_named_graph_name,
                               osm_csv_file, osm_mapping_file, osm_kg_file,
                               osm_hn_csv_file, osm_hn_mapping_file, osm_hn_kg_file,
                               osm_time_description={}):

    """
    Fonction pour faire l'ensemble des processus relatifs à la création des factoïdes pour les données d'OSM
    """

    # Création d'un répertoire des factoïdes pour les données d'OSM
    msp.create_factoid_repository(graphdb_url, repository_name, namespace_prefixes, tmp_folder, ont_file, ontology_named_graph_name, disable_same_as=False, clear_if_exists=True)

    # Récupération des URI des graphes nommés
    factoids_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, factoids_named_graph_name))
    permanent_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, permanent_named_graph_name))

    # A partir des fichiers csv décrivant les adresses d'OSM dans Paris, convertir en un graphe de connaissance selon le mapping défini
    # Puis import du graphe dans le répertoire dont le nom est `repository_name` et dans le graphe nommé donné par `named_graph_name`
    msp.from_raw_to_data_to_graphdb(graphdb_url, ontorefine_url, ontorefine_cmd, repository_name, factoids_named_graph_name, osm_csv_file, osm_mapping_file, osm_kg_file)
    msp.from_raw_to_data_to_graphdb(graphdb_url, ontorefine_url, ontorefine_cmd, repository_name, factoids_named_graph_name, osm_hn_csv_file, osm_hn_mapping_file, osm_hn_kg_file)

    # Nettoyage du graphe
    clean_osm_graph(graphdb_url, repository_name, factoids_named_graph_uri, permanent_named_graph_uri)

    # Ajout d'éléments manquants (changements et événéments)
    msp.add_missing_elements_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri)
    msp.add_missing_elements_for_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri)

    # Ajouter des approximations sur les événéments qui n'ont pas de valeur temporelle
    msp.create_time_resources_for_current_sources(graphdb_url, repository_name, factoids_named_graph_uri, osm_time_description)

    # L'URI ci-dessous définit la source liée à OSM
    osm_source_uri = URIRef("http://rdf.geohistoricaldata.org/id/address/facts/Source_OSM")
    create_source_osm(graphdb_url, repository_name, osm_source_uri, permanent_named_graph_uri)

    # Transfert de triplets non modifiables vers le graphe nommé permanent
    msp.transfert_immutable_triples(graphdb_url, repository_name, factoids_named_graph_uri, permanent_named_graph_uri)
    
    # Ajout de liens entre les ressources de type repère et la source
    msp.add_factoids_resources_links(graphdb_url, repository_name, factoids_named_graph_uri)

# Données venant de fichiers Geojson

def create_landmark_from_geojson_feature(feature:dict, landmark_type:str, g:Graph, namespace_prefixes:dict, srs_uri:URIRef=None, lang:str=None):
    label = feature.get("properties").get("name")

    if srs_uri is None:
        geometry = gp.from_geojson_to_wkt(feature.get("geometry"))
    else:
        geometry = srs_uri.n3() + " " + gp.from_geojson_to_wkt(feature.get("geometry"))

    geometry_lit = Literal(geometry, datatype=namespace_prefixes["geo"]["wktLiteral"])
    landmark_uri = gr.generate_uri(namespace_prefixes["factoids"], "LM")

    gr.create_landmark(landmark_uri, label, lang, landmark_type, g, namespace_prefixes["addr"], namespace_prefixes["ltype"])
    g.add((landmark_uri, namespace_prefixes["geo"]["asWKT"], geometry_lit))
        
    # landmark_uri = gr.generate_uri(namespace_prefixes["factoids"], "LM")
    # name_attribute_uri = gr.generate_uri(namespace_prefixes["factoids"], "ATTR")
    # geom_attribute_uri = gr.generate_uri(namespace_prefixes["factoids"], "ATTR")
    
    # gr.create_landmark_with_changes(landmark_uri, name_version, lang, landmark_type, g,
    #                              namespace_prefixes["addr"], namespace_prefixes["factoids"], namespace_prefixes["ltype"], namespace_prefixes["ctype"])
    # gr.create_landmark_attribute(name_attribute_uri, landmark_uri, "Name", g, namespace_prefixes["addr"], namespace_prefixes["atype"])
    # gr.create_landmark_attribute(geom_attribute_uri, landmark_uri, "Geometry", g, namespace_prefixes["addr"], namespace_prefixes["atype"])
    # gr.create_attribute_version(name_attribute_uri, name_version, g, namespace_prefixes["addr"], namespace_prefixes["factoids"], namespace_prefixes["ctype"], lang=lang)
    # gr.create_attribute_version(geom_attribute_uri, geom_version, g, namespace_prefixes["addr"], namespace_prefixes["factoids"], namespace_prefixes["ctype"], datatype=geom_datatype)

def create_landmarks_from_geojson_feature_collection(feature_collection:dict, landmark_type:str, g:Graph, namespace_prefixes:dict, lang:str=None):
    crs_dict = {
        "urn:ogc:def:crs:OGC:1.3:CRS84" : URIRef("http://www.opengis.net/def/crs/EPSG/0/4326"), 
        "urn:ogc:def:crs:EPSG::2154" :  URIRef("http://www.opengis.net/def/crs/EPSG/0/2154"), 
    }

    features = feature_collection.get("features")
    geojson_crs = feature_collection.get("crs")
    srs_iri = get_srs_iri_from_geojson_feature_collection(geojson_crs, crs_dict)
    
    for feature in features:
        create_landmark_from_geojson_feature(feature, landmark_type, g, namespace_prefixes, srs_iri, lang=lang)

def get_srs_iri_from_geojson_feature_collection(geojson_crs, crs_dict):  
    try:
        crs_name = geojson_crs.get("properties").get("name")
        srs_iri = crs_dict.get(crs_name)
        return srs_iri
    except:
        return None
    
def create_landmark_graph_from_feature_collection(features_collection, out_kg_file, landmark_type:str,namespace_prefixes:dict,lang:str=None):
    g = Graph()
    create_landmarks_from_geojson_feature_collection(features_collection, landmark_type, g, namespace_prefixes, lang)
    g.serialize(out_kg_file)

def create_factoid_process_geojson(graphdb_url, repository_name, namespace_prefixes, tmp_folder,
                                   ont_file, ontology_named_graph_name,
                                   factoids_named_graph_name, permanent_named_graph_name,
                                   geojson_content, geojson_join_property, kg_file, landmark_type, lang:str=None):

    """
    Fonction pour faire l'ensemble des processus relatifs à la création des factoïdes pour les données issues d'un fichier Geojson
    """

    # Lire le fichier geojson et fusionner les éléments selon `geojson_join_property`. Par exemple, si `geojson_join_property="name"`, la fonction fusionne toutes les features qui ont le même nom.
    geojson_features = gp.merge_geojson_features_from_one_property(geojson_content, geojson_join_property)
    geojson_time = geojson_content.get("time")
    geojson_source = geojson_content.get("source")

    # Création d'un répertoire des factoïdes pour les données
    msp.create_factoid_repository(graphdb_url, repository_name, namespace_prefixes, tmp_folder, ont_file, ontology_named_graph_name, disable_same_as=False, clear_if_exists=True)

    # Récupération des URI des graphes nommés
    factoids_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, factoids_named_graph_name))
    permanent_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, permanent_named_graph_name))

    # À partir du fichier geojson décrivant des repères (qui sont tous du même type), convertir en un graphe de connaissance selon l'ontologie
    create_landmark_graph_from_feature_collection(geojson_features, kg_file, landmark_type, namespace_prefixes, lang)

    # Importer le fichier `kg_file` qui a été créé lors de la ligne précédente dans le répertoire `repository_name`, dans le graphe nommé `factoids_named_graph_name` 
    gd.import_ttl_file_in_graphdb(graphdb_url, repository_name, kg_file, factoids_named_graph_name)

    # # Suppression des instants qui n'ont aucun timeStamp (instants sans date)
    # msp.remove_time_instant_without_timestamp(graphdb_url, repository_name)

    # Nettoyer les données en fusionnant les doublons après l'import dans GraphDB
    clean_geojson_graph(graphdb_url, repository_name, factoids_named_graph_uri, permanent_named_graph_uri)

    # Ajout d'éléments manquants (changements et événéments)
    msp.add_missing_elements_for_landmarks(graphdb_url, repository_name, factoids_named_graph_uri)
    msp.add_missing_elements_for_landmark_relations(graphdb_url, repository_name, factoids_named_graph_uri)

    # Ajout des données temporelles (si elles existent)
    msp.create_time_resources(graphdb_url, repository_name, factoids_named_graph_uri, geojson_time)

    # # L'URI ci-dessous définit la source liée à la BAN
    geojson_source_uri = URIRef(gr.generate_uri(namespace_prefixes["facts"], "SRC"))
    create_source_geojson(graphdb_url, repository_name, geojson_source_uri, permanent_named_graph_uri, geojson_source, namespace_prefixes["facts"])

    # Transfert de triplets non modifiables vers le graphe nommé permanent
    msp.transfert_immutable_triples(graphdb_url, repository_name, factoids_named_graph_uri, permanent_named_graph_uri)
    
    # # Ajout de liens entre les ressources de type repère et la source
    geojson_source_prov_uri = URIRef(gr.generate_uri(namespace_prefixes["facts"], "PROV"))
    create_source_provenances_geojson(graphdb_url, repository_name, geojson_source_uri, geojson_source_prov_uri, factoids_named_graph_uri, permanent_named_graph_uri)

def create_source_geojson(graphdb_url, repository_name, source_uri:URIRef, named_graph_uri:URIRef, geojson_source:dict, facts_namespace:Namespace):
    """
    Création de la source relative aux données du fichier Geojson
    """

    lang = geojson_source.get("lang")
    source_label_str = geojson_source.get("label")
    source_label = Literal(source_label_str, lang=lang)

    prefixes = """
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#> 
    PREFIX facts: <http://rdf.geohistoricaldata.org/id/address/facts/>
    PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>
    """
    
    query = prefixes + f"""
    INSERT DATA {{
        GRAPH {named_graph_uri.n3()} {{
            {source_uri.n3()} a rico:Record ; rdfs:label {source_label.n3()} 
        }}
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

    # Ajout du publisher s'il existe
    publisher = geojson_source.get("publisher")
    if publisher is not None:
        publisher_label_str = publisher.get("label")
        publisher_uri = URIRef(gr.generate_uri(facts_namespace, "PUB"))
        publisher_label = Literal(publisher_label_str, lang=lang)

        query = prefixes + f"""
        INSERT DATA {{
            GRAPH {named_graph_uri.n3()} {{
                {source_uri.n3()} rico:hasPublisher {publisher_uri.n3()}.
                {publisher_uri.n3()} a rico:CorporateBody ; rdfs:label {publisher_label.n3()}
            }}
        }}
        """

        gd.update_query(query, graphdb_url, repository_name)

def create_source_provenances_geojson(graphdb_url, repository_name, source_uri:URIRef, source_prov_uri:URIRef, factoids_named_graph_uri:URIRef, permanent_named_graph_uri:URIRef):
    """
    Création des liens de provenances entre la source et les données d'un fichier Geojson
    """

    prefixes = """
    PREFIX : <http://rdf.geohistoricaldata.org/def/address#> 
    PREFIX facts: <http://rdf.geohistoricaldata.org/id/address/facts/>
    PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>
    PREFIX prov: <http://www.w3.org/ns/prov#>
    """
    
    query = prefixes + f"""
    INSERT {{
        GRAPH {factoids_named_graph_uri.n3()} {{
            ?elem prov:wasDerivedFrom {source_prov_uri.n3()}. 
        }}
        GRAPH {permanent_named_graph_uri.n3()} {{
            {source_prov_uri.n3()} a prov:Entity; rico:isOrWasDescribedBy {source_uri.n3()}.
        }}
    }}
    WHERE {{
        ?elem a ?elemType.
        FILTER(?elemType IN (:Landmark, :LandmarkRelation, :AttributeVersion, :Change, :Event, :TemporalEntity))
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def clean_geojson_graph(graphdb_url, repository_name, factoids_named_graph_uri, permanent_named_graph_uri):
    prefixes = """
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX rico: <https://www.ica.org/standards/RiC/ontology#>
    PREFIX geofla: <http://data.ign.fr/def/geofla#>
    PREFIX addr: <http://rdf.geohistoricaldata.org/def/address#>
    PREFIX ltype: <http://rdf.geohistoricaldata.org/id/codes/address/landmarkType/>
    """

    query1 = prefixes + f"""
    DELETE {{
            ?hn ?p ?o.
            ?s ?p ?hn.
        }}
    WHERE {{
        ?hn a addr:Landmark; addr:isLandmarkType ltype:HouseNumber.
        MINUS {{?lr a addr:LandmarkRelation; addr:locatum ?hn; addr:relatum [a addr:Landmark; addr:isLandmarkType ?thoroughfare] }}
        {{?hn ?p ?o.}}UNION{{?s ?p ?hn.}}
    }}
    """
    
    queries = [query1]
    for query in queries:
        gd.update_query(query, graphdb_url, repository_name) 