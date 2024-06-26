import os
import filemanagement as fm
import ttlmanagement as ttlm
import curl as curl
import urllib.parse as up
from rdflib import Graph, Namespace, Literal, BNode, URIRef
from rdflib.namespace import RDF
import json

def get_repository_uri_from_name(graphdb_url, repository_name):
    return f"{graphdb_url}/repositories/{repository_name}"

def get_graph_uri_from_name(graphdb_url, repository_name, graph_name):
    return f"{graphdb_url}/repositories/{repository_name}/rdf-graphs/{graph_name}"

def get_repository_uri_statements_from_name(graphdb_url, repository_name):
    return f"{graphdb_url}/repositories/{repository_name}/statements"

def remove_graph(graphdb_url, repository_name, graph_name):
    cmd = curl.get_curl_command("DELETE", get_graph_uri_from_name(graphdb_url, repository_name, graph_name))
    os.system(cmd)

def remove_graph_from_uri(graph_uri:URIRef):
    cmd = curl.get_curl_command("DELETE", graph_uri.strip())
    os.system(cmd)

def remove_graphs(graphdb_url,repository_name,graph_name_list):
    for g in graph_name_list:
        remove_graph(graphdb_url, repository_name, g)

def create_config_local_repository_file(config_repository_file:str, repository_name:str, ruleset_file:str="rdfsplus-optimized", disable_same_as:bool=True):
    rep = Namespace("http://www.openrdf.org/config/repository#")
    sr = Namespace("http://www.openrdf.org/config/repository/sail#")
    sail = Namespace("http://www.openrdf.org/config/sail#")
    graph_db = Namespace("http://www.ontotext.com/config/graphdb#")
    g = Graph()

    elem = BNode()
    repository_impl = BNode()
    sail_impl = BNode()
    
    disable_same_as_str = str(disable_same_as).lower()
    g.add((elem, RDF.type, rep.Repository))
    g.add((elem, rep.repositoryID, Literal(repository_name)))
    g.add((elem, rep.repositoryImpl, repository_impl))
    g.add((repository_impl, rep.repositoryType, Literal("graphdb:SailRepository")))
    g.add((repository_impl, sr.sailImpl, sail_impl))
    g.add((sail_impl, sail.sailType, Literal("graphdb:Sail")))
    g.add((sail_impl, graph_db["base-URL"], Literal("http://example.org/owlim#")))
    g.add((sail_impl, graph_db["defaultNS"], Literal("")))
    g.add((sail_impl, graph_db["entity-index-size"], Literal("10000000")))
    g.add((sail_impl, graph_db["entity-id-size"], Literal("32")))
    g.add((sail_impl, graph_db["imports"], Literal("")))
    g.add((sail_impl, graph_db["repository-type"], Literal("file-repository")))
    g.add((sail_impl, graph_db["ruleset"], Literal(ruleset_file)))
    g.add((sail_impl, graph_db["storage-folder"], Literal("storage")))
    g.add((sail_impl, graph_db["enable-context-index"], Literal("false")))
    g.add((sail_impl, graph_db["enablePredicateList"], Literal("true")))
    g.add((sail_impl, graph_db["in-memory-literal-properties"], Literal("true")))
    g.add((sail_impl, graph_db["enable-literal-index"], Literal("true")))
    g.add((sail_impl, graph_db["check-for-inconsistencies"], Literal("false")))
    g.add((sail_impl, graph_db["disable-sameAs"], Literal(disable_same_as_str)))
    g.add((sail_impl, graph_db["query-timeout"], Literal("0")))
    g.add((sail_impl, graph_db["query-limit-results"], Literal("0")))
    g.add((sail_impl, graph_db["throw-QueryEvaluationException-on-timeout"], Literal("false")))
    g.add((sail_impl, graph_db["read-only"], Literal("false")))
    
    g.serialize(destination=config_repository_file)

def reinfer_repository(graphdb_url, repository_name):
    """
    According to GraphDB : 'Statements are inferred only when you insert new statements. So, if reconnected to a repository with a different ruleset, it does not take effect immediately.'
    This function reinfers repository
    """
    
    query = """
    prefix sys: <http://www.ontotext.com/owlim/system#>
    INSERT DATA { [] sys:reinfer [] }
    """

    update_query(query, graphdb_url, repository_name)

def create_repository_from_config_file(graphdb_url:str, local_config_file:str):
    url = f"{graphdb_url}/rest/repositories"
    curl_cmd_local = curl.get_curl_command("POST", url, content_type="multipart/form-data", form=f"config=@{local_config_file}")
    os.system(curl_cmd_local)

def export_data_from_repository(graphdb_url, repository_name, out_ttl_file, named_graph_uri:URIRef=None):
    query_param = ""
    if named_graph_uri is not None:
        named_graph_uri_encoded = up.quote(named_graph_uri.n3())
        query_param += f"?context={named_graph_uri_encoded}"

    url = get_repository_uri_statements_from_name(graphdb_url, repository_name) + query_param
    cmd = curl.get_curl_command("GET", url, content_type="application/x-www-form-urlencoded", accept="text/turtle")

    out_content = os.popen(cmd)
    fm.write_file(out_content.read(), out_ttl_file)

def select_query_to_txt_file(query, graphdb_url, repository_name, res_query_file):
    query_encoded = up.quote(query)
    post_data = f"query={query_encoded}"
    cmd = curl.get_curl_command("POST", get_repository_uri_from_name(graphdb_url, repository_name), content_type="application/x-www-form-urlencoded", post_data=post_data)
    out_content = os.popen(cmd)
    fm.write_file(out_content.read(), res_query_file)

def select_query_to_json(query, graphdb_url, repository_name):
    query_encoded = up.quote(query)
    post_data = f"query={query_encoded}"
    cmd = curl.get_curl_command("POST", get_repository_uri_from_name(graphdb_url, repository_name), content_type="application/x-www-form-urlencoded", accept="application/json", post_data=post_data)
    out_content = os.popen(cmd)
    return json.loads(out_content.read())

def update_query(query, graphdb_url, repository_name):
    url = get_repository_uri_statements_from_name(graphdb_url, repository_name)
    query_encoded = up.quote(query)
    cmd = curl.get_curl_command("POST", url, content_type="application/x-www-form-urlencoded", post_data=f"update={query_encoded}")
    os.system(cmd)

def get_repository_namespaces(graphdb_url, repository_name):
    namespaces_uri = get_repository_uri_from_name(graphdb_url, repository_name) + "/namespaces"
    cmd = curl.get_curl_command("GET", namespaces_uri)
    namespaces_list = os.popen(cmd).read().split("\n")[1:]
    namespaces = {}

    for namespace in namespaces_list:
        try:
            prefix, uri = namespace.split(",")
            namespaces[prefix] = uri
        except ValueError:
            pass

    return namespaces

def add_prefix_to_repository(graphdb_url, repository_name, namespace:Namespace, prefix:str):
    url = get_repository_uri_from_name(graphdb_url, repository_name) + "/namespaces/" + prefix
    cmd = curl.get_curl_command("PUT", url, content_type="text/plain", post_data=namespace.strip())
    os.system(cmd)

def add_prefixes_to_repository(graphdb_url, repository_name, namespace_prefixes:dict):
    for prefix, namespace in namespace_prefixes.items():
        add_prefix_to_repository(graphdb_url, repository_name, namespace, prefix)

def get_repository_prefixes(graphdb_url, repository_name, perso_namespaces:dict=None):
    """
    perso_namespaces is a dictionnary which stores personalised namespaces to add of overwrite repository namespaces.
    keys are prefixes and values are URIs
    Ex: `{"geo":"http://data.ign.fr/def/geofla"}`
    """

    namespaces = get_repository_namespaces(graphdb_url, repository_name)
    if perso_namespaces is not None:
        namespaces.update(perso_namespaces)

    prefixes = ""
    for prefix, uri in namespaces.items():
        prefixes += f"PREFIX {prefix}: <{uri}>\n"
        
    return prefixes

### Import created ttl file in GraphDB
def import_ttl_file_in_graphdb(graphdb_url, repository_id, ttl_file, graph_name=None, graph_uri=None):
    # cmd = f"curl -X POST -H \"Content-Type:application/x-turtle\" -T \"{ttl_file}\" {graphdb_url}/repositories/{repository_id}/statements"
    if graph_uri is not None:
        url = graph_uri
    elif graph_name is not None:
        url = get_graph_uri_from_name(graphdb_url, repository_id, graph_name)
    else:
        url = get_repository_uri_statements_from_name(graphdb_url, repository_id)
    
    cmd = curl.get_curl_command("POST", url, content_type="application/x-turtle", local_file=ttl_file)
    msg = os.popen(cmd)
    return msg.read()

def upload_ttl_folder_in_graphdb_repository(ttl_folder_name, graphdb_url, repository_id, graph_name, limit:int=float("inf")):
    nb_elem = 0
    for elem in os.listdir(ttl_folder_name):
        elem_path = os.path.join(ttl_folder_name, elem)
        if os.path.splitext(elem)[-1].lower() == ".ttl":
            nb_elem += 1
            msg = import_ttl_file_in_graphdb(graphdb_url, repository_id, elem_path, graph_name)
            # Création d'un fichier temporel sans URI problématique pour l'import si y a un problème.
            if "Invalid IRI value" in msg:
                nb_elem -= 1
                tmp_elem_path = elem_path.replace(".ttl", "_tmp.ttl")
                ttlm.format_ttl_to_avoid_invalid_iri_value_error(elem_path, tmp_elem_path)
                msg = import_ttl_file_in_graphdb(graphdb_url, repository_id, tmp_elem_path, graph_name)
                os.remove(tmp_elem_path)
        if nb_elem >= limit:
            return None

def clear_named_graph_of_repository(graphdb_url, repository_name, named_graph_uri:URIRef):
    """
    Remove all contents from repository
    The repository still exists
    """
    named_graph_uri_encoded = up.quote(named_graph_uri.n3())
    url = f"{graphdb_url}/repositories/{repository_name}/statements?context={named_graph_uri_encoded}"
    cmd = curl.get_curl_command("DELETE", url)
    os.system(cmd)

def clear_repository(graphdb_url, repository_name):
    """
    Remove all contents from repository
    The repository still exists
    """
    url = f"{graphdb_url}/repositories/{repository_name}/statements"
    cmd = curl.get_curl_command("DELETE", url, content_type="application/x-turtle")
    os.system(cmd)

def remove_repository(graphdb_url, repository_name):
    """
    Remove a repository defined by its name
    """
    url = f"{graphdb_url}/repositories/{repository_name}"
    cmd = curl.get_curl_command("DELETE", url, content_type="application/x-turtle")
    os.system(cmd)