import os
import json
import csv

def read_file(filename, split_lines=False):
    file = open(filename, "r")
    file_content = file.read()
    if split_lines:
        file_content = file_content.split("\n")
    file.close()
    return file_content

def read_json_file(filename):
    file = open(filename)
    data = json.load(file)
    file.close()
    return data

def write_file(content,filename):
    file = open(filename, "w")
    file.write(content)
    file.close()

def create_folder_if_not_exists(folder):
    if not os.path.exists(folder):
        os.makedirs(folder)

def remove_folder_if_exists(folder):
    if os.path.exists(folder):
        remove_folder(folder)

def remove_folder(folder):
    for e in os.listdir(folder):
        abspath_e = os.path.join(folder, e)
        print(abspath_e)
        if os.path.isfile(abspath_e):
            remove_file_if_exists(abspath_e)
        elif os.path.isdir(abspath_e):
            remove_folder(e)
        else:
            print(e)

    os.rmdir(folder)
        
def remove_file_if_exists(filename):
    if os.path.exists(filename):
        os.remove(filename)

def write_csv_file_from_rows(rows:list[list], filename):
    with open(filename, 'w') as f:     
        file = csv.writer(f)
        file.writerows(rows)

def read_csv_file(csv_file, has_header=False, delimiter=",", quotechar='"', encoding='utf-8'):
    file =  open(csv_file, 'r', encoding=encoding)
    csvreader = csv.reader(file, delimiter=delimiter, quotechar=quotechar)
    if has_header:
        header = next(csvreader)
    else:
        header = []
    rows = []
    for row in csvreader:
        rows.append(row) 

    file.close()

    return header, rows