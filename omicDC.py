import argparse
import pandas as pd
import numpy as np
import dask.dataframe as dd
import time
import dask
from dask.distributed import Client
from dask.diagnostics import ProgressBar
from dask.distributed import progress

import multiprocessing
import os

from joblib import Parallel, delayed, load, dump
from Sparse_vector.sparse_vector import SparseVector

#defines

PRIVATE_PATH = "/home/avoitetskii/private_omicON.txt"

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

#cmd line module init
cmd_line = argparse.ArgumentParser(description='Script for parsing and saving omic data')
# add fields to parser
cmd_line.add_argument(
    '--id',
    '-i',
    type=str,
    default=None,
    help='Experimental ID'
)

cmd_line.add_argument(
    '--assembly',
    '-g',
    type=str,
    default="hg38",
    help='Genome assembly'
)

cmd_line.add_argument(
    '--antigen_class',
    '-b',
    type=str,
    default=None,
    help='Antigen class'
)

cmd_line.add_argument(
    '--antigen',
    '-a',
    type=str,
    default=None,
    help='Antigen'
)

cmd_line.add_argument(
    '--cell_type',
    '-t',
    type=str,
    default=None,
    help='Cell type class'
)

cmd_line.add_argument(
    '--cell',
    '-c',
    type=str,
    default=None,
    help='Cell type'
)

cmd_line.add_argument(
    '--file',
    '-f',
    type=str,
    default="hg38",
    help='Path to export files'
)


cmd_line.add_argument(
    '--verbose',
    '-v',
    type=int,
    default=1,
    help='verbose operation'
)


def get_matching_experimnet_part(
            df, 
            num,
            options
        ):
    # num - chunk number
    # options - list of arguments
    part = df.partitions[num]
    
    for key in options.keys():
        if options[key]:
            tmp = options[key].split(',')
            part = part.loc[part[key].isin(tmp)]
    part = part.compute()
    return part


def create_matching_expirement_df(
            que, 
            filename, 
            options
        ): #    Return expirement names list
    

    # match_exp_df - df for matching experiments
    match_exp_df = pd.read_csv(
                    FILE_PATH + filename,

                    sep = '\t', 
                    names = ['id', 'Genome assembly', 'Antigen class', 'Antigen', 'Cell type class', 'Cell type'],
                    usecols=range(6)
                )
    if args.verbose:
        print("Find file " +  FILE_PATH + filename)

    for key in options.keys():
        if options[key]:
            tmp = options[key].split(',')
            match_exp_df = match_exp_df.loc[match_exp_df[key].isin(tmp)]

    return match_exp_df


def add_sorted_bed_2_file( 
            filename,
            df,
            num,
            matching_experiments
        ): 
    part = df.partitions[num]

    part = part.loc[part['id'].isin(matching_experiments)]
    part = part.compute()
    part.to_csv(filename, index=False, header=False, mode='a')
    return num


def create_sorted_bed_file(
        que,
        filename,
        match_exp_df
    ):


    path_2_sorted_file = FILE_PATH + "filtred_" + filename + ".csv"

    process_list = []

    matching_experiments = list(match_exp_df.loc[:,'id'])

    df = dd.read_csv(   
                FILE_PATH + filename,
                sep = "\t", 
                names = ["chr", 'begin', 'end', 'id', 'score'],
                blocksize = '100mb'
                )

    open(path_2_sorted_file, mode = 'w').close()  # Creating empty .csv for editing
    
    for part in range(df.npartitions):
        process_list.append(que.submit(
                                add_sorted_bed_2_file,  
                                path_2_sorted_file,
                                df,
                                part,
                                matching_experiments
                                )) 
    #TODO progress bar
    if args.verbose: 
        print(f"Your file creating. You can see progress here:\n http://{IP}:{PORT}/status\n")

        print(f"{bcolors.OKCYAN}Progress bar is not working yet. Whatever ??\_(???)_/??\nW8 a bit{bcolors.ENDC}")
    a = [process.result() for process in process_list]
    progress(a)
    


def create_feature(
        key,
        exps,
        sizes,
        filename
    ):
    
    # chroms - list with chroms of the organism
    chroms = list(sizes.keys())
    
    # data - dict with values of exp for each cromosome
    data = {chrm: np.zeros(sizes[chrm], dtype=np.uint16) for chrm in chroms}
    
    # exp_df - df with selected rows from chip-atlas bed file
    exp_df = pd.read_csv(FILE_PATH + "filtred_" + filename + ".csv", header=None, sep=',')
    exp_df = exp_df[exp_df[3].isin(exps)]
    exp_df = exp_df[exp_df[0].isin(chroms)]
    
    for line in exp_df.values:
        chrm, begin, end, ee, value = line
        data[chrm][begin: end] = np.maximum(data[chrm][begin: end], value)
    
    # data_sparse - convert data to sparse
    data_sparse = {chrm:SparseVector(data[chrm]) for chrm in chroms}
    
    os.makedirs('data', exist_ok=True)
    dump(data_sparse, "data/" + "_".join(key) + ".pkl", 3)


def create_features_files(
	match_exp_df,
	gen_assembly,
	filename
    ):
    
    # sizes - dict with cromosome as key and it's len as value
    sizes = pd.read_csv(FILE_PATH + gen_assembly + '.chrom.sizes', sep='\t', header=None)
    sizes = dict(sizes.values)
    
    Parallel(n_jobs=int(NCORES))(delayed(create_feature)(key, list(loc_df['id']), sizes, filename) 
                   for key, loc_df in match_exp_df.groupby(['Antigen class', 'Antigen class']))
    
        

def parse_private():
    d = {}
    with open(PRIVATE_PATH) as f:
        for line in f:
            if str(line) == '___Doc_list___\n':
                if args.verbose:
                    print('___Doc_list___')
                continue
            (key, val) = line.split()
            d[str(key)] = val

            if args.verbose:
                print(key, ':', val)
    return(d)   


if __name__ == '__main__':
    
    args = cmd_line.parse_args()

    print(f"{bcolors.OKCYAN}Be aware of bugs{bcolors.ENDC}")

    hyperparametrs = parse_private()
    
    NCORES  = int(hyperparametrs["NCORES"])
    NWORKERS = int(hyperparametrs["NWORKERS"])
    IP = hyperparametrs["IP"]
    PORT    =   hyperparametrs["PORT"]
    FILE_PATH = hyperparametrs["file_path"]
     

    que = Client(n_workers=NCORES, threads_per_worker=NWORKERS)

    options = {
        #Parse arguments from cmd line to special dict
        "id"                :   args.id,
        "Genome assembly"   :   args.assembly,
        "Antigen class"     :   args.antigen_class,
        "Antigen"           :   args.antigen,
        "Cell type class"   :   args.cell_type,
        "Cell type'"        :   args.cell
    }
    for key in options.keys():
        if options[key]:
            options[key] = options[key].replace('_', ' ')
    
    if args.verbose: 
        print("Succes parse arguments!")
        for key,value in options.items():
            print(key, ':', value)

    match_exp_df = create_matching_expirement_df(que, "experimentList.tab", options)
    
    if args.verbose:
        print(f"Was finded {len(match_exp_df)} results:\n " + str(match_exp_df.head()))
    
    create_sorted_bed_file(que, hyperparametrs[args.assembly], match_exp_df)


    que.shutdown()
    if args.verbose: 
        print('Feature creation started')
    create_features_files(match_exp_df, args.assembly, hyperparametrs[args.assembly])
    print('Feature creation fineshed')
    os.remove(FILE_PATH + "filtred_" + hyperparametrs[args.assembly] + ".csv")
    
