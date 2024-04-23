# Peuplement multi-sources de l'ontologie
Peuplement de l'ontologie via différentes sources

## Sources
Les sources utilisées ici sont :
* la nomenclature des voies de la Ville de Paris ;
* OpenStreetMap (OSM) ;
* Wikidata ;
* Base Adresse Nationale (BAN).

## Dossier `data`
Ce dossier contient des fichiers qui servent de données de départ au peuplement. Huit fichiers sont nécessaires dont les noms sont données dans le notebook par les variables suivantes :
* `vpta_csv_file_name` : fichier des dénominations des emprises des voies actuelles de la Ville de Paris ;
* `vptc_csv_file_name` : fichier des dénominations des caduques des voies la Ville de Paris ;
* `osm_csv_file_name` : fichier des données extraites d'OpenStreetMap ;
* `osm_hn_csv_file_name` : fichier des données de numéros d'immeubles d'OpenStreetMap ;
* `bpa_csv_file_name` : fichier des données issues de la BAN ;
* `wdpt_csv_file_name` : fichier des voies de Paris venant de Wikidata ;
* `wdpa_csv_file_name` : fichier des zones liées à Paris venant de Wikidata ;
* `wdpl_csv_file_name` : fichier des relations d'entités géographiques (entre voies et zones liée à Paris) venant de Wikidata.

La manière d'obtenir les fichiers sont indiqués ci-dessous.

### Ville de Paris
* Les données de la ville de Paris sont composées de deux jeux :
* [dénominations des emprises des voies actuelles](https://opendata.paris.fr/explore/dataset/denominations-emprises-voies-actuelles)
* [dénominations caduques des voies](https://opendata.paris.fr/explore/dataset/denominations-des-voies-caduques)

Les informations utilisées ici sont les noms des voies (et leur emprise géographique pour les voies actuelles) avec leur période temporelle de validité (si elle est connue).

Il faut télécharger les deux jeux de données en format CSV dans le dossier `data` et leur nom doivent correspondre aux noms données par les variables `vpta_csv_file_name` (pour les voies actuelles) et `vptc_csv_file_name` pour les voies caduques.

### OpenStreetMap

Les données extraites d'OSM sont :
- les numéros d'immeubles (_house numbers_) : leur valeur (leur numéro), leur géométrie, leur appartenance à une voie et à un arrondissement ;
- les voies : leur nom
- les arrondissements : leur nom et leur code INSEE. 

Il faut extraire ces données et les enregistrer dans deux fichiers. Pour cela, il suffit de se rendre sur [QLever](https://qlever.cs.uni-freiburg.de/osm-planet), voir *Bast, H., Brosi, P., Kalmbach, J., & Lehmann, A. (2021, November). An efficient RDF converter and SPARQL endpoint for the complete OpenStreetMap data. In Proceedings of the 29th International Conference on Advances in Geographic Information Systems (pp. 536-539)*.

1. Extraction des adresses de Paris
Dans l'interface de requêtage de QLever, il y a deux requêtes à lancer.
* Requête 1 :
```
PREFIX osmrel: <https://www.openstreetmap.org/relation/>
PREFIX osmkey: <https://www.openstreetmap.org/wiki/Key:>
PREFIX osmrdf: <https://osm2rdf.cs.uni-freiburg.de/rdf/member#>
PREFIX osm: <https://www.openstreetmap.org/>
PREFIX ogc: <http://www.opengis.net/rdf#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT DISTINCT ?houseNumberId ?streetId ?streetName ?arrdtId ?arrdtName ?arrdtInsee
 WHERE {
  ?selectedArea osmkey:wikidata "Q90"; ogc:sfContains ?houseNumberId.
  ?houseNumberId osmkey:addr:housenumber ?housenumberName.
  ?arrdtId ogc:sfContains ?houseNumberId; osmkey:name ?arrdtName; osmkey:ref:INSEE ?arrdtInsee; osmkey:boundary "administrative"; osmkey:admin_level "9"^^xsd:int .
  ?streetId osmkey:type "associatedStreet"; osmrel:member ?member; osmkey:name ?streetName.
  ?member osmrdf:role "house"; osmrdf:id ?houseNumberId.
}
```

* Requête 2 : 
```
PREFIX osmkey: <https://www.openstreetmap.org/wiki/Key:>
PREFIX ogc: <http://www.opengis.net/rdf#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>

SELECT DISTINCT ?houseNumberId ?housenumberName ?houseNumberGeomWKT
 WHERE {
  ?selectedArea osmkey:wikidata "Q90"; ogc:sfContains ?houseNumberId.
  ?houseNumberId osmkey:addr:housenumber ?housenumberName; geo:hasGeometry ?houseNumberGeom.
  ?houseNumberGeom geo:asWKT ?houseNumberGeomWKT.
}
```

Les requêtes sélectionnent l'ensemble des numéros d'immeuble de Paris mais il est possible de changer la zone d'extraction en modifiant la condition `osmkey:wikidata "Q90"`. Par exemple, on peut remplacer par `osmkey:wikidata "Q387285"` pour se restreindre au quartier des Halles de Paris. Attention, seuls les numéros d'immeuble appartenant à une relation de type `associatedStreet` en ayant le rôle `house` dans cette relation sont sélectionnés.

2. Export du résultat dans deux fichiers `csv` et insertion de ces derniers dans le dossier défini par la variable `tmp_folder`. Le nom des fichiers doivent correspondre à ceux définis dans le notebook :
* pour la requête 1, le nom est liée à la variable `osm_csv_file_name` ;
* pour la requête 2, le nom est celui de `osm_hn_csv_file_name`.

### Wikidata

Via Wikidata, les données extraites sont 
* les voies de Paris
* les zones en lien avec Paris :
  * quartiers de Paris ;
  * arrondissements (ceux d'avant et d'après 1860) de Paris ;
  * communes (anciennes et actuelles) de l'ancien département de la Seine ;
* les relations entre ces entités géographiques.

Trois fichiers en format CSV doivent être stockés dans le dossier `data` dont les noms sont liés à des variables du notebook :
* `wdpt_csv_file_name` pour les voies de Paris ;
* `wdpa_csv_file_name` pour les zones en lien avec Paris ;
* `wdpl_csv_file_name` pour les relations entre les entités géographiques.

La manière d'obtenir ces fichiers se fait simplement. Il suffit de lancer la fonction `get_data_from_wikidata()` définie dans le notebook.

### Base Adresse Nationale

Les données issues de la [Base Adresse Nationale (BAN)](https://adresse.data.gouv.fr/base-adresse-nationale) sont accessibles [ici](https://adresse.data.gouv.fr/data/ban/adresses/latest/csv). Pour ce travail, il convient de télécharger les données liées à Paris (soit celles du département n°75). Le fichier téléchargé est au format CSV qui doit être mis dans le dossier `data`, le nom de ce fichier doit correspondre à la variable `bpa_csv_file_name` du notebook.

## Lancement du processus
Une fois que les fichiers sont présents dans le dossier `data`, le processus peut être lancé.

⚠️ Toutefois, il faut s'assurer que deux logiciels sont installés et ils devront tourner durant le processus :
* [Ontotext Refine](https://www.ontotext.com/products/ontotext-refine/) (ou OntoRefine) qui permet d'automatiser la conversion de données textuelles en un graphe de connaissances. Dans la section des variables globables (voir ci-dessous), deux variables sont liées au logiciel :
  * `ontorefine_cli` : chemin absolu de l'interface en ligne de commande (CLI) d'OntoRefine. Pour trouver ce chemin, il suffit de cliquer sur le bouton `Open CLI directory` présent sur l'interface de lancement du logiciel. Cela vous renvoie vers le dossier contenant la CLI dont le nom est `ontorefine-cli`.
  * `ontorefine_url` : l'URL de l'application web.  Pour trouver cette valeur, il suffit de cliquer sur le bouton `Open Refine web application` présent sur l'interface de lancement du logiciel. La valeur à associer à `ontorefine_url` est l'url à laquelle on enlève `/projects`.
* [GraphDB](https://graphdb.ontotext.com/) qui permet de stocker et de travailler sur des graphes de connaissance. Une variable est associée au logiciel : `graphdb_url` qui est l'URL de l'application web. Le procédé est similaire à celui de `ontorefine_url` pour trouver sa valeur.

![Interface d'OntoRefine avec les boutons \`Open Refine web application\` et \`Open CLI directory\`](./images/interface_ontorefine.png)
