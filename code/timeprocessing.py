import os
import datetime
from rdflib import Graph, Namespace, Literal, BNode, URIRef, XSD
from rdflib.namespace import RDF
import graphdb as gd

def get_query_to_compare_time_instants(time_named_graph_uri:URIRef, query_prefixes:str, time_instant_select_conditions:str):
    """"
    `time_instant_select_conditions` defines conditions to select two instants which have to be compared : ?ti1 and ?ti2
    """
    query = query_prefixes + f"""
    INSERT {{
        GRAPH ?g {{
            ?ti1 ?timeProp ?ti2 .
            ?ti1 ?predSameTime ?ti2 .

        }}
    }}
    WHERE {{
        BIND ({time_named_graph_uri.n3()} AS ?g)

        {time_instant_select_conditions}

        ?ti1 a addr:CrispTimeInstant; addr:timeStamp ?ts1; addr:timeCalendar ?tc; addr:timePrecision ?tp1.
        ?ti2 a addr:CrispTimeInstant; addr:timeStamp ?ts2; addr:timeCalendar ?tc; addr:timePrecision ?tp2.
        FILTER (?ti1 != ?ti2 &&?ts1 <= ?ts2)

        BIND(YEAR(?ts1) = YEAR(?ts2) AS ?sameYear)
        BIND(MONTH(?ts1) = MONTH(?ts2) AS ?sameMonth)
        BIND(DAY(?ts1) = DAY(?ts2) AS ?sameDay)

        BIND(IF(time:unitMillenium in (?tp1, ?tp2), FLOOR(YEAR(?ts1)/1000) = FLOOR(YEAR(?ts2)/1000),
                IF(time:unitCentury in (?tp1, ?tp2), FLOOR(YEAR(?ts1)/100) = FLOOR(YEAR(?ts2)/100),
                    IF(time:unitDecade in (?tp1, ?tp2), FLOOR(YEAR(?ts1)/10) = FLOOR(YEAR(?ts2)/10),
                        IF(time:unitYear in (?tp1, ?tp2), ?sameYear,
                            IF(time:unitMonth in (?tp1, ?tp2), ?sameYear && ?sameMonth,
                                IF(time:unitDay in (?tp1, ?tp2), ?sameYear && ?sameMonth && ?sameDay,
                                    "false"^^xsd:boolean)
                            ))))) AS ?sameTime)

        BIND(IF(?tp1 = time:unitMillenium, "1"^^xsd:integer, 
                IF(?tp1 = time:unitCentury, "2"^^xsd:integer,
                    IF(?tp1 = time:unitDecade, "3"^^xsd:integer,
                        IF(?tp1 = time:unitYear, "4"^^xsd:integer,
                            IF(?tp1 = time:unitMonth, "5"^^xsd:integer,
                                IF(?tp1 = time:unitDay, "6"^^xsd:integer,
                                    "0"^^xsd:integer)
                            ))))) AS ?ti1prec)

        BIND(IF(?tp2 = time:unitMillenium, "1"^^xsd:integer, 
                IF(?tp2 = time:unitCentury, "2"^^xsd:integer,
                    IF(?tp2 = time:unitDecade, "3"^^xsd:integer,
                        IF(?tp2 = time:unitYear, "4"^^xsd:integer,
                            IF(?tp2 = time:unitMonth, "5"^^xsd:integer,
                                IF(?tp2 = time:unitDay, "6"^^xsd:integer,
                                    "0"^^xsd:integer)
                            ))))) AS ?ti2prec)

        BIND(IF(?ti1prec > ?ti2prec, time:lessPreciseThan, 
                IF(?ti1prec < ?ti2prec, time:morePreciseThan, time:asPreciseAs
                )) AS ?precisonPred)
                
        OPTIONAL {{
            FILTER(?sameTime)
            BIND(IF(?precisonPred = time:asPreciseAs, owl:sameAs, ?precisonPred) AS ?predSameTime)
        }}

        BIND(IF(?sameTime, time:same, time:before) AS ?timeProp)
    }}
    """

    return query

def get_query_to_compare_time_intervals(time_named_graph_uri:URIRef, query_prefixes:str, time_interval_select_conditions:str):
    query = query_prefixes + f"""
    INSERT {{
        GRAPH ?g {{
            ?i1 time:intervalBefore ?i2
        }}
    }}
    WHERE {{
        BIND({time_named_graph_uri.n3()} AS ?g)
        {time_interval_select_conditions}
        
        ?av1 addr:hasTime ?i1 .
        ?av2 addr:hasTime ?i2 .
        ?i1 addr:hasEnd ?i1end .
        ?i2 addr:hasBeginning ?i2beg .
        ?i1end time:before ?i2beg .
    }} ;

    INSERT {{
        GRAPH ?g {{
            ?i1 time:intervalMeets ?i2
        }}
    }}
    WHERE {{
        BIND({time_named_graph_uri.n3()} AS ?g)
        {time_interval_select_conditions}
        
        ?av1 addr:hasTime ?i1 .
        ?av2 addr:hasTime ?i2 .
        ?i1 addr:hasEnd ?i1end .
        ?i2 addr:hasBeginning ?i2beg .
        ?i1end time:same ?i2beg .
    }} ;

    INSERT {{
        GRAPH ?g {{
            ?i1 time:intervalOverlaps ?i2
        }}
    }}
    WHERE {{
        BIND({time_named_graph_uri.n3()} AS ?g)
        {time_interval_select_conditions}
        
        ?av1 addr:hasTime ?i1 .
        ?av2 addr:hasTime ?i2 .
        ?i1 addr:hasBeginning ?i1beg ; addr:hasEnd ?i1end .
        ?i2 addr:hasBeginning ?i2beg ; addr:hasEnd ?i2end .
        ?i1beg time:before ?i2beg .
        ?i1end time:after ?i2beg .
        ?i1end time:before ?i2end .
    }} ;

    INSERT {{
        GRAPH ?g {{
            ?i1 time:intervalStarts ?i2
        }}
    }}
    WHERE {{
        BIND({time_named_graph_uri.n3()} AS ?g)
        {time_interval_select_conditions}
        
        ?av1 addr:hasTime ?i1 .
        ?av2 addr:hasTime ?i2 .
        ?i1 addr:hasBeginning ?i1beg ; addr:hasEnd ?i1end .
        ?i2 addr:hasBeginning ?i2beg ; addr:hasEnd ?i2end .
        ?i1beg time:same ?i2beg .
        ?i1end time:before ?i2end .
    }} ;

    INSERT {{
        GRAPH ?g {{
            ?i1 time:intervalDuring ?i2
        }}
    }}
    WHERE {{
        BIND({time_named_graph_uri.n3()} AS ?g)
        {time_interval_select_conditions}
        
        ?av1 addr:hasTime ?i1 .
        ?av2 addr:hasTime ?i2 .
        ?i1 addr:hasBeginning ?i1beg ; addr:hasEnd ?i1end .
        ?i2 addr:hasBeginning ?i2beg ; addr:hasEnd ?i2end .
        ?i1beg time:after ?i2beg .
        ?i1end time:before ?i2end .
    }} ;

    INSERT {{
        GRAPH ?g {{
            ?i1 time:intervalFinishes ?i2
        }}
    }}
    WHERE {{
        BIND({time_named_graph_uri.n3()} AS ?g)
        {time_interval_select_conditions}
        
        ?av1 addr:hasTime ?i1 .
        ?av2 addr:hasTime ?i2 .
        ?i1 addr:hasBeginning ?i1beg ; addr:hasEnd ?i1end .
        ?i2 addr:hasBeginning ?i2beg ; addr:hasEnd ?i2end .
        ?i1beg time:after ?i2beg .
        ?i1end time:same ?i2end .
    }} ;

    INSERT {{
        GRAPH ?g {{
            ?i1 time:intervalEquals ?i2
        }}
    }}
    WHERE {{
        BIND({time_named_graph_uri.n3()} AS ?g)
        {time_interval_select_conditions}
        
        ?av1 addr:hasTime ?i1 .
        ?av2 addr:hasTime ?i2 .
        ?i1 addr:hasBeginning ?i1beg ; addr:hasEnd ?i1end .
        ?i2 addr:hasBeginning ?i2beg ; addr:hasEnd ?i2end .
        ?i1beg time:same ?i2beg .
        ?i1end time:same ?i2end .
    }}
    """

    return query


def compare_time_instants_of_events(graphdb_url, repository_name, query_prefixes:str, time_named_graph_uri:URIRef):
    """
    Sort all time instants related to one event.
    """
    
    time_instant_select_conditions = "?ev a addr:Event ; ?tpred1 ?ti1 ; ?tpred2 ?ti2 ."
    query = get_query_to_compare_time_instants(time_named_graph_uri, query_prefixes, time_instant_select_conditions)

    gd.update_query(query, graphdb_url, repository_name)

def compare_time_instants_of_attributes(graphdb_url, repository_name, query_prefixes:str, time_named_graph_uri:URIRef):
    """
    Sort all time instants related to one attribute.
    """
    
    time_instant_select_conditions = """
        ?attr a addr:Attribute ; addr:changedBy ?cg1, ?cg2.
        ?cg1 a addr:AttributeChange ; addr:dependsOn [?tpred1 ?ti1] .
        ?cg2 a addr:AttributeChange ; addr:dependsOn [?tpred2 ?ti2] .
        """
    
    query = get_query_to_compare_time_instants(time_named_graph_uri, query_prefixes, time_instant_select_conditions)

    gd.update_query(query, graphdb_url, repository_name)

def compare_time_intervals_of_attribute_versions(graphdb_url, repository_name, query_prefixes:str, time_named_graph_uri:URIRef):
    """
    Sort all time intervals of versions related to one attribute.
    """
    
    time_interval_select_conditions = """
        ?attr a addr:Attribute ; addr:hasAttributeVersion ?av1, ?av2 .
        FILTER (?av1 != ?av2)
        """
    
    query = get_query_to_compare_time_intervals(time_named_graph_uri, query_prefixes, time_interval_select_conditions)

    gd.update_query(query, graphdb_url, repository_name)

def get_earliest_and_latest_time_instants_for_events(graphdb_url, repository_name, query_prefixes:str, time_named_graph_uri:URIRef):
    """
    An event can get related to multiple instants through addr:hasTimeBefore and addr:hasTimeAfter. This function gets the latest and the earliest time instant for each event.
    """
    
    query = query_prefixes + f"""
    INSERT {{
        GRAPH ?g {{
            ?ev ?estPred ?t
        }}
    }}
    WHERE {{
        BIND({time_named_graph_uri.n3()} AS ?g)
        {{
            BIND(addr:hasTimeAfter AS ?erPred)
            BIND(addr:hasEarliestTimeInstant AS ?estPred)
            BIND(time:after AS ?compPred)
        }} UNION {{
            BIND(addr:hasTimeBefore AS ?erPred)
            BIND(addr:hasLatestTimeInstant AS ?estPred)
            BIND(time:before AS ?compPred)
        }}
        ?ev a addr:Event ; ?erPred ?t
        MINUS {{
            ?ev ?erPred ?tbis .
            ?tbis ?compPred ?t .
        }}
        MINUS {{
            ?ev ?erPred ?tbis .
            ?tbis time:morePreciseThan ?t .
            ?tbis time:same ?t .
        }}
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def remove_earliest_and_latest_time_instants(graphdb_url, repository_name, query_prefixes:str, time_named_graph_uri:URIRef):
    """
    """

    query = query_prefixes + f"""
    DELETE {{
        GRAPH ?g {{
            ?s ?p ?o
        }}
    }}
    WHERE {{
        BIND({time_named_graph_uri.n3()} AS ?g)
        ?s ?p ?o .
        FILTER(?p IN (addr:hasLatestTimeInstant, addr:hasEarliestTimeInstant))
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def get_validity_interval_for_attribute_versions(graphdb_url, repository_name, query_prefixes:str, time_named_graph_uri:URIRef):

    query = query_prefixes + f"""
    INSERT {{
        GRAPH ?g {{
            ?av addr:hasTime ?timeInterval .
            ?timeInterval a addr:CrispTimeInterval ; addr:hasBeginning ?ti1 ; addr:hasEnd ?ti2 .
        }}
    }}
    WHERE {{
        BIND({time_named_graph_uri.n3()} AS ?g)

        ?av a addr:AttributeVersion; addr:isMadeEffectiveBy ?cg1; addr:isOutdatedBy ?cg2.
        ?cg1 a addr:AttributeChange; addr:dependsOn ?ev1.
        ?cg2 a addr:AttributeChange; addr:dependsOn ?ev2.
        OPTIONAL {{?ev1 addr:hasTime ?tip1}}
        OPTIONAL {{?ev2 addr:hasTime ?tip2}}
        OPTIONAL {{?ev1 addr:hasLatestTimeInstant ?til1 .}}
        OPTIONAL {{?ev2 addr:hasLatestTimeInstant ?til2 .}}
        OPTIONAL {{?ev1 addr:hasEarliestTimeInstant ?tie1 .}}
        OPTIONAL {{?ev2 addr:hasEarliestTimeInstant ?tie2 .}}
        
        FILTER(BOUND(?tip1) || BOUND(?til1) || BOUND(?tie1))
        FILTER(BOUND(?tip2) || BOUND(?til2) || BOUND(?tie2))

        BIND(IF(BOUND(?tip1), ?tip1, IF(BOUND(?til1), ?til1, ?tie1)) AS ?ti1)
        BIND(IF(BOUND(?tip2), ?tip2, IF(BOUND(?tie2), ?tie2, ?til2)) AS ?ti2)
        BIND(URI(CONCAT(STR(URI(facts:)), "TI_", STRUUID())) AS ?timeInterval)
    }}
    """

    gd.update_query(query, graphdb_url, repository_name)

def add_time_relations(graphdb_url:str, repository_name:str, namespace_prefixes:dict, time_named_graph_name:str):
    """
    Ajout de relations temporelles :
    * comparaison des instants appartenant à un même événement (i1 before/after i2)
    * comparaison des instants liés à un même attribut (i1 before/after i2)
    * déduction des instants au plus tôt / au plus tard liés aux événéments à partir des instants avant / après
    * création d'intervalles de validité pour des versions d'attributs
    * comparaison des intervalles de versions entre versions d'un même attribut

    L'ensemble des triplets est stocké dans le graphe nommé dont le nom est `time_named_graph_name`.
    """
    
    time_named_graph_uri = URIRef(gd.get_named_graph_uri_from_name(graphdb_url, repository_name, time_named_graph_name))
    prefixes = gd.get_query_prefixes_from_namespaces(namespace_prefixes)
    compare_time_instants_of_events(graphdb_url, repository_name, prefixes, time_named_graph_uri)
    compare_time_instants_of_attributes(graphdb_url, repository_name, prefixes, time_named_graph_uri)
    get_earliest_and_latest_time_instants_for_events(graphdb_url, repository_name, prefixes, time_named_graph_uri)
    get_validity_interval_for_attribute_versions(graphdb_url, repository_name, prefixes, time_named_graph_uri)
    remove_earliest_and_latest_time_instants(graphdb_url, repository_name, prefixes, time_named_graph_uri)
    compare_time_intervals_of_attribute_versions(graphdb_url, repository_name, prefixes, time_named_graph_uri)