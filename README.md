# ProteomeGenerator2
## Introduction
ProteomeGenerator 2 (PG2) is a versatile, Linux cluster-oriented pipeline for integrated proteogenomic analysis built on the Snakemake infrastructure. Its main module utilizes variant calls (VCF files) and RNA-seq data (FASTQ/BAM files) to generate comprehensive, individualized protein sequence databases to be used in protein mass spectrometry searches. 

## Overview of ProteomeGenerator 2
Briefly, proteome generation works like this: first, variant calls are used to “patch” the reference genome, yielding one that is specific to the sample(s) in question. Next, RNA-seq reads are aligned (STAR) to the newly individualized genome, from which the complete transcriptome is assembled (StringTie) in either a de novo or annotation-guided manner and corresponding nucleotide sequences are read out. Finally, the nucleotide sequences are 6-frame translated, the most probable open reading frame(s) for each transcript are selected based on length of longest contiguous peptide sequence and homology to known proteoforms, and mapped back to the genome to produce the individualized proteome database. By combining arbitrary sets of sequencing/structural/etc variant calls with de novo transcriptome assembly, PG2’s databases are able to capture a diverse and extensible breadth of genomic and transcriptomic variation.

In addition to its primary proteome generation functionality, PG2 also packages in UltraQuant, a Linux-compatible plug-n-play installation of the popular proteomics suite MaxQuant (achieved by leveraging a Singularity container running a compatible version of Mono). Furthermore, post-proteomics modules are provided to map identified non-canonical / unannotated peptides back to the genetic events from which they derive. Finally, implementations of the GATK Best Practices pipelines for WGS/WES alignment and germline/somatic short variant calling are also bundled into the release, allowing the entire proteogenomic analysis, from raw sequencing data to novel protein identifications and mapping, to be carried out in a single command.

## Modules
PG2 is organized into the following modules, each of which can be run on its own, or invoked (recursively) as a subworkflow/submodule:

- `ProteomeGenerator2.py` (RNA-seq / main proteome generation module) : the main executable file of PG2. This module contains the rules for RNA-seq mapping, transcriptome and fusion transcript assembly, protein prediction, and MaxQuant. It can optionally invoke the genome individualization module as a *subworkflow* (meaning it runs before the module’s own rules run). It also imports the novel analysis module rules for post-proteomics search analysis.
- `genome_personalization_module.py` : contains the rules for taking a VCF file and creating an individualized bi-haploid genome (sequence FASTA + annotation GTF) for downstream analysis. It can optionally invoke the variant calling module as a subworkflow, or ingest a premade VCF.

- `WGS_variant_calling.py` : contains the rules for taking a pre-processed, analysis-ready BAM file and calling variants to produce a germline and/or somatic VCF that can be used for genome individualization (or other purposes). It can optionally invoke the WGS pre-processing module as a subworkflow, or ingest a pre-processed BAM. 

- `WGS_preprocessing.py` : contains the rules for aligning and pre-processing raw FASTQ reads or an unprocessed BAM file in preparation for variant calling. Will typically be invoked by the variant calling module as a subworkflow. 

- `novel_analysis.py` : contains the rules for aggregating novel peptides identified on MaxQuant proteomics search (as weand mapping them back to their originating mutations. Also in development are rules for deconvoluting non-mutational novel peptides (from de novo isoforms, upstream start sites, upstream ORFs, etc) and for rudimentary protein expression analysis.

## Installation

### Required packages

- Miniconda for Python 3 (version >= 4.8.3) 
- Snakemake (version >= 5.4.5) 
- Singularity (version >= 2.4.2)

All other packages and libraries will be managed by Snakemake (via conda) and do not need to be installed by the user.

### Recommended Installation Steps

1.	Install Singularity
    - This is already installed on the Lilac cluster, and most likely on the majority of Linux clusters. 

2.	Install Miniconda for Python 3 -- https://conda.io/en/latest/miniconda.html
    - Copy the Linux installer link to clipboard
    - In Lilac terminal, enter `wget <installer_link>` to download the installer shell script
    - Enter `./<installer_sh>` to run the installation script, make sure to enter yes when asked if conda should be added to the PATH

3.	Install mamba (conda repository manager)
    - `conda install -c conda-forge mamba`

4.	Install snakemake as a new conda environment
    - `mamba create -c conda-forge -c bioconda -n snakemake snakemake`

5.	Activate the snakemake environment
    - `conda activate snakemake`

6.	Download PG2
    - `git clone https://github.com/kentsisresearchgroup/ProteomeGenerator2.git`

## Input Data

The fully incorporated pipeline utilizes the following data:

1.	Paired-end whole-genome/whole-exome sequencing data OR variant call data
(used to create the individualized genome that produces individualized protein sequences)
    -	WGS/WES data can be in either FASTQ/BAM format, or both
    -	Variant calls should be in VCF format (untested as of now)

2.	RNA-seq data (paired- or single-end)
    -	FASTQ/BAM format, or both

3.	Raw MS/MS data
    -	ThermoFisher RAW files
    -	Other formats (e.g. mzML, MGF) should also work (albeit untested)

Based on the workflow defined by the user in the configuration file, not all types of input data will necessarily be used in a given run.

## Configuration File (configfile)
The configfile is a YAML file that is written in an intentionally verbose style to make it easy for a non-technical audience to understand. It is a hierarchically organized file <with parent-child relationships denoted by a two space indentation [SPACEBAR twice]> whose top-level categories are as follows:

•	**Directories**

•	**“Stock” genome and proteome references**

•	**User-defined workflow**

•	**Input files**

•	**Parameters**

These categories are largely self-explanatory; additionally, the documentation/comments provided in the configfile itself is verbose, so the user is best directed there directly to begin learning to use it. We provide a few templates and examples in the configfiles/ directory. Please make sure to read through the entire configfile the first time through, to get a full idea of the parameters that are configurable by the user.

In general, the structure of the configfile should not be changed. Doing so will usually cause the program to break. The exception to this is in the input files section, for which sample/readgroup/file/etc subsections should be duplicated to accommodate multiple entries. 

## Usage 

### Basic Command

The (suggested) snakemake command to run PG2 takes the following general form:

`snakemake --snakefile ProteomeGenerator2.py --cluster "bsub -J {params.J} -n {params.n} -R 'span[hosts=1] rusage[mem={params.mem_per_cpu}]' -W 144:00 -o {params.o} -eo {params.eo}" -j 100 -k --ri --latency-wait 30 \
--configfile configfiles/PG2_template.yaml --use-conda --use-singularity --singularity-args "--bind /data:/data,/lila:/lila,/scratch:/scratch" -n --quiet`

It looks really complicated at first, but keep in mind that most of it doesn’t change from run to run, so you can pretty much copy & paste it for each run, with minor modifications. A brief rundown of the parameters:

### Sanity checks recommended before every pipeline run:
`-n` = dry run. Lists out every pipeline rule that will be executed with the given command. Without --quiet, includes specification of inputs, outputs, and “wildcard” parameters. Extremely useful sanity check, highly recommend running this before every run.
`--quiet` = reduces the verbosity of the run/dry-run terminal output to print only the names of the rules being run, without input/output/wildcards. Suggested to include in dry-run command before kicking off a full pipeline run (as command list can be quite unwieldy with subworkflows etc.), but would remove prior to the actual run.

### Parameters that user will change regularly:
`--configfile <configfile.yaml>` = where the workflow is defined, and all directories/files/parameters are set
`<output_file>` = the ‘target’, or final output of the pipeline desired by the user
`--snakefile <snakefile.py>` = the main snakemake (Python) program to execute (for PG2, this is ProteomeGenerator2.py)  this will vary only if the user wants to run the various submodules (pre-processing, variant calling, etc) independently of the main program

### Parameters the user will likely have to change once before first execution:
`--cluster “<cluster_specific_string>”` = parameters for compute cluster execution (the Lilac cluster uses the LSF scheduler, which deploys jobs via the command bsub). {params.<parameter>} binds the corresponding parameters of the params section of each Snakemake rule, to the cluster command. This will need to be edited for use with SLURM, Oracle Grid Engine, etc.
[here, J=jobname, n=cores, R=host/memory spec, W=wall time, o=output log, eo=error log]
`--singularity-args “--bind <filesystem_bindings>”` = grants Singularity containers permission to access other directories within the local filesystem

### Parameters the user will likely (and probably should) never change: 
`--use-conda` = allows use of packages and environments from Anaconda
`--use-singularity` = allows use of plug-n-play containers (PG2 uses Singularity specifically for MaxQuant, which requires particular versions of mono to run on Linux)
`-k` = when a job fails, continue executing independent jobs
`--ri` = rerun incomplete jobs automatically

For the full parameter specifications, please see the Snakemake official documentation at https://snakemake.readthedocs.io/en/stable/. 

## Output files
The usage of PG2 follows the general paradigm of Snakemake, in which the user specifies, in the snakemake command, the final output file(s) they wish to produce. Snakemake then identifies the rule (every pipeline step is defined by a rule) that produces the target output file, and then works backwards to string together the set of rules (represented by a DAG) needed to generate the output files, until reaching the input files. 

**Default case**: If no particular output file(s) are specified, then Snakemake will default to the files specified in the “all” rule of the Snakefile in question (for PG2, the Snakefile will typically be ProteomeGenerator2.py). Here are the default output files specified in rule all: 
-	`out/{study_group}/combined.proteome.unique.fasta` : the primary output proteome database. This is a non-redundant (unique) set of customized protein sequences, which is created by combining and de-duplicating the databases from the parallel haplotype runs (which themselves are located at out/{study_group}/haplotype-{1,2}/transcriptome/proteome.fasta). This combined database is what is used as the search database for the proteomics module.

-	`out/{study_group}/combined.proteome.bed` : the BED file corresponding to the aforementioned proteome database, with coordinates lifted back to the original stock genome coordinate space (for easy visualization in IGV). The bedfiles in custom genome coordinate space for each haplotype run are located at /out/{study_group}/haplotype-{1,2}/transcriptome/proteome_preLiftBack.bed.

-	`out/{study_group}/MaxQuant/combined/txt/summary.txt` : the significance of this file is that its presence signifies the completion of a MaxQuant run. The main output tables such as peptides.txt, proteinGroups.txt, msms.txt, etc. are also contained within the same directory. Summary.txt itself contains various metrics about the run, both separated by raw file and in aggregate.

-	`out/{study_group}/novel_analysis/{mutation_type}/combined.{mutation_type}.map` : Map of all variants of a given mutation type that appear in the proteome database. Thus far this has been implemented for {missense, insertions, deletions, frameshifts}. Additionally, combined.{mutation\_type}\_MQevidence.map maps mutations to MaxQuant (MQ) evidence, and combined.novelPep\_{mutation\_type}.map maps MQ-identified non-canonical peptides to their originating mutations.

