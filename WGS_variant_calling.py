import os
PG2_HOME = config['directories']['PG2_installation_dir']
WD = config['directories']['working_and_output_dir']
workdir: WD

STOCK_GENOME_FASTA=config['stock_references']['genome']['fasta']
STOCK_GENOME_GTF=config['stock_references']['genome']['gtf']


input_file_format = config['input_files']['genome_personalization_module']['input_file_format']
try: config['input_files']['genome_personalization_module'][input_file_format+'_inputs']
except: raise TypeError("ERROR: Specified inputs do not match the specified input file format.")

COHORT = config['input_files']['genome_personalization_module']['cohort_or_organism_name']
TUMOR_SAMPLES=[]
NORMAL_SAMPLES=[]
sample_dict = dict(config['input_files']['genome_personalization_module'][input_file_format+'_inputs'])
for sample_name in sample_dict.keys():
    if sample_dict[sample_name]['matched_sample_params']['is_matched_sample'] == False or sample_dict[sample_name]['matched_sample_params']['tumor_or_normal']=='tumor': TUMOR_SAMPLES.append(sample_name)
    elif sample_dict[sample_name]['matched_sample_params']['tumor_or_normal']=='normal': 
        NORMAL_SAMPLES.append(sample_name)
    else: assert False, "This should never happen!"
ALL_SAMPLES=TUMOR_SAMPLES + NORMAL_SAMPLES

ANALYSIS_READY_BAMFILES=[]
SAMPLEFILE_SAMPLENAME_DICT=dict()
for sample in TUMOR_SAMPLES:
    filename = "out/WGS/variant_calling/tumor/{}.analysis_ready.bam".format(sample)
    ANALYSIS_READY_BAMFILES.append(filename)
    SAMPLEFILE_SAMPLENAME_DICT[filename] = sample
for sample in NORMAL_SAMPLES:
    filename = "out/WGS/variant_calling/normal/{}.analysis_ready.bam".format(sample)
    ANALYSIS_READY_BAMFILES.append(filename)
    SAMPLEFILE_SAMPLENAME_DICT[filename] = sample

VARIANT_CALLING_MODES=[]
if config['user_defined_workflow']['genome_personalization_module']['variant_calling_submodule']['call_germline_variants_with_GATK4_HaplotypeCaller']==True: VARIANT_CALLING_MODES.append('germline')
if NORMAL_SAMPLES and config['user_defined_workflow']['genome_personalization_module']['variant_calling_submodule']['if_inputs_are_matched_tumor-normal_samples']['call_somatic_variants_with_GATK4_Mutect2']==True: VARIANT_CALLING_MODES.append('somatic')

running_preprocessing = config['user_defined_workflow']['genome_personalization_module']['variant_calling_submodule']['run_pre-processing_steps']
just_ran_WGS_preprocessing = config['user_defined_workflow']['genome_personalization_module']['variant_calling_submodule']['continuation']['just_ran_PG2_preprocessing']

subworkflow WGS_preprocessing:
    snakefile: "WGS_preprocessing.py"
    configfile: workflow.overwrite_configfile
    workdir: WD

snakemake.utils.makedirs('out/logs/intervals')
snakemake.utils.makedirs('out/logs/variant_calling')
snakemake.utils.makedirs('out/logs/variant_calling/chr-wise')
snakemake.utils.makedirs('out/logs/variant_calling/intervals')
NUM_VARIANT_INTERVALS = config['parameters']['genome_personalization_module']['variant_calling']['advanced']['variant_intervals_scatter']
rule var_00_ScatterVariantCallingIntervals:
    input: config['parameters']['genome_personalization_module']['variant_calling']['resources']['wgs_calling_regions']
    output: "out/WGS/intervals/{interval}-scattered.interval_list"
    params: n="1", R="'span[hosts=1] rusage[mem=8]'", \
            o="out/logs/intervals/{interval}.out", eo="out/logs/intervals/{interval}.err", \
            J="generate_intervals_{interval}"
    conda: "envs/gatk4.yaml"
    shell: "gatk --java-options '-Xmx8g' SplitIntervals \
              -R {STOCK_GENOME_FASTA} -L {input} -scatter {NUM_VARIANT_INTERVALS} -O out/WGS/intervals"

if (not just_ran_WGS_preprocessing) and running_preprocessing:
    rule var_00_SymlinkToPreProcessingOutputBam:
        input: bam=WGS_preprocessing("out/WGS/{tumor_or_normal}/{sample}.aligned_sorted_ubam-merged_RG-merged_dedup_fixedtags_BQSR.analysis_ready.bam"),bai=WGS_preprocessing("out/WGS/{tumor_or_normal}/{sample}.aligned_sorted_ubam-merged_RG-merged_dedup_fixedtags_BQSR.analysis_ready.bai")
        output: bam="out/WGS/variant_calling/{tumor_or_normal}/{sample}.analysis_ready.bam",bai="out/WGS/variant_calling/{tumor_or_normal}/{sample}.analysis_ready.bam.bai"
        params: n="1",R="'span[hosts=1]'",o="out/logs/variant_calling/symlink.out",eo="out/logs/variant_calling/symlink.err",J="symlink"
        run: 
            in_bam_path = os.path.abspath(input.bam)
            in_bai_path = os.path.abspath(input.bai)
            command = "ln -s {} {}; ln -s {} {}".format(in_bam_path, output.bam, in_bai_path, output.bai)
            shell(command)

elif just_ran_WGS_preprocessing:
    rule var_00_SymlinkToPreProcessingOutputBam:
        input: bam="out/WGS/{tumor_or_normal}/{sample}.aligned_sorted_ubam-merged_RG-merged_dedup_fixedtags_BQSR.analysis_ready.bam",bai="out/WGS/{tumor_or_normal}/{sample}.aligned_sorted_ubam-merged_RG-merged_dedup_fixedtags_BQSR.analysis_ready.bai"
        output: bam="out/WGS/variant_calling/{tumor_or_normal}/{sample}.analysis_ready.bam",bai="out/WGS/variant_calling/{tumor_or_normal}/{sample}.analysis_ready.bam.bai"
        params: n="1",R="'span[hosts=1]'",o="out/logs/variant_calling/symlink.out",eo="out/logs/variant_calling/symlink.err",J="symlink"
        run: 
            in_bam_path = os.path.abspath(input.bam)
            in_bai_path = os.path.abspath(input.bai)
            command = "ln -s {} {}; ln -s {} {}".format(in_bam_path, output.bam, in_bai_path, output.bai)
            shell(command)

else:
    PROCESSED_BAM_DICT=dict(config['input_files']['genome_personalization_module']['bam_inputs'])
    all_bams_preprocessed = True
    for sample_name in PROCESSED_BAM_DICT.keys():
        if not PROCESSED_BAM_DICT[sample_name]['pre-processing_already_complete']: all_bams_preprocessed = False
    assert(input_file_format=='bam' and all_bams_preprocessed), "ERROR: Variant calling is turned on, but WGS/WES pre-processing is turned off. Therefore all input files must be coordinate-sorted, duplicate-marked, analysis-ready BAMs. Please ensure that this is the case, and if so that the corresponding parameters are set (i.e. input_files->genome_personalization_module->input_file_format = 'bam'; input_files->genome_personalization_module->bam_inputs-><sample>->pre-processing_already_complete = true). Please also double check that pre-processing was not disabled erroneously."
    rule var_00_SymlinkToUserPreprocessedBam:
        input: bam=lambda wildcards: os.path.abspath(config['input_files']['genome_personalization_module']['bam_inputs'][wildcards.sample]['bam_file']),bai=lambda wildcards: os.path.abspath(config['input_files']['genome_personalization_module']['bam_inputs'][wildcards.sample]['bai_file'])
        output: bam="out/WGS/variant_calling/{tumor_or_normal}/{sample}.analysis_ready.bam",bai="out/WGS/variant_calling/{tumor_or_normal}/{sample}.analysis_ready.bai"
        params: n="1",R="'span[hosts=1]'",o="out/logs/variant_calling/symlink.out",eo="out/logs/variant_calling/symlink.err",J="symlink"
        shell: "ln -s {input.bam} {output.bam}; ln -s {input.bai} {output.bai}"

rule var_germ_01_CallGermlineVariantsPerInterval:
    input: bam="out/WGS/variant_calling/{tumor_or_normal}/{sample}.analysis_ready.bam", interval_list="out/WGS/intervals/{interval}-scattered.interval_list"
    output: "out/WGS/variant_calling/{tumor_or_normal}/HTC-scattered/{sample}.HTC.{interval}.g.vcf"
    params: n="4", R="'span[hosts=1] rusage[mem=3]'", \
        o="out/logs/intervals/vcf_{interval}.out", eo="out/logs/intervals/vcf_{interval}.err", \
        J="generate_vcf_{interval}"
    conda: "envs/gatk4.yaml"
    shell: "gatk --java-options '-Xmx12g' HaplotypeCaller -R {STOCK_GENOME_FASTA} -I {input.bam} -O {output} -L {input.interval_list} -ERC GVCF"

rule var_germ_02_GenotypeTumorSamplePerInterval:
    input: gvcf="out/WGS/variant_calling/{tumor_or_normal}/HTC-scattered/{sample}.HTC.{interval}.g.vcf", interval_list="out/WGS/intervals/{interval}-scattered.interval_list"
    output: "out/WGS/variant_calling/{tumor_or_normal}/HTC-scattered/{sample}.HTC.{interval}.genotyped.vcf"
    params: n="2", R="'span[hosts=1] rusage[mem=32]'", \
        o="out/logs/intervals/genotype_gvcfs_{interval}.out", eo="out/logs/intervals/genotype_gvcfs_{interval}.err", \
        J="genotype_gvcfs"
    conda: "envs/gatk4.yaml"
    shell: "gatk --java-options '-Xmx64g' GenotypeGVCFs -R {STOCK_GENOME_FASTA} \
              -V {input.gvcf} -L {input.interval_list} -O {output}"

"""
rule var_germ_03_CNN1D_ScoreVariants:
    input: bam="out/WGS/variant_calling/{tumor_or_normal}/{sample}.analysis_ready.bam",vcf="out/WGS/variant_calling/{tumor_or_normal}/HTC-scattered/{sample}.HTC.{interval}.genotyped.vcf",interval_list="out/WGS/intervals/{interval}-scattered.interval_list"
    output: "out/WGS/variant_calling/{tumor_or_normal}/HTC-scattered/{sample}.HTC.{interval}.CNN-scored.vcf.gz"
    params: n="1", R="'span[hosts=1] rusage[mem=8]'", \
        o="out/logs/intervals/score_variants_{interval}.out", eo="out/logs/intervals/score_variants_{interval}.err", \
        J="score_variants_{interval}"
    singularity: "docker://broadinstitute/gatk:4.1.4.1"
    shell: "gatk --java-options '-Xmx8g' CNNScoreVariants -R {STOCK_GENOME_FASTA} -V {input.vcf} -O {output} -L {input.interval_list}"

"""

rule var_germ_03_CNN2D_ScoreVariants:
    input: bam="out/WGS/variant_calling/{tumor_or_normal}/{sample}.analysis_ready.bam",vcf="out/WGS/variant_calling/{tumor_or_normal}/HTC-scattered/{sample}.HTC.{interval}.genotyped.vcf",interval_list="out/WGS/intervals/{interval}-scattered.interval_list"
    output: "out/WGS/variant_calling/{tumor_or_normal}/HTC-scattered/{sample}.HTC.{interval}.CNN-scored.vcf.gz"
    params: n="1", R="'span[hosts=1] rusage[mem=8]'", \
        o="out/logs/intervals/score_variants_{interval}.out", eo="out/logs/intervals/score_variants_{interval}.err", \
        J="score_variants_{interval}"
    singularity: "docker://broadinstitute/gatk:4.1.4.1"
    shell: "gatk --java-options '-Xmx8g' CNNScoreVariants -R {STOCK_GENOME_FASTA} -I {input.bam} -V {input.vcf} -O {output} -L {input.interval_list} --tensor-type read_tensor"

HAPMAP=config['parameters']['genome_personalization_module']['variant_calling']['resources']['germline']['snps_db']
MILLS=config['parameters']['genome_personalization_module']['variant_calling']['resources']['germline']['indels_db']
SNP_TRANCHE=config['parameters']['genome_personalization_module']['variant_calling']['advanced']['snp_tranche']
INDEL_TRANCHE=config['parameters']['genome_personalization_module']['variant_calling']['advanced']['indel_tranche']
rule var_germ_04_AssignVariantTranches:
    input: vcf="out/WGS/variant_calling/{tumor_or_normal}/HTC-scattered/{sample}.HTC.{interval}.CNN-scored.vcf.gz",interval_list="out/WGS/intervals/{interval}-scattered.interval_list"
    output: temp("out/WGS/variant_calling/{tumor_or_normal}/HTC-scattered/{sample}.HTC.{interval}.CNN-scored.tranched.vcf.gz")
    params: n="1", R="'span[hosts=1] rusage[mem=4]'", \
        o="out/logs/assign_tranches.out", eo="out/logs/assign_tranches.err", \
        J="assign_tranches"
    singularity: "docker://broadinstitute/gatk:4.1.4.1"
    shell: "gatk --java-options '-Xmx4g' FilterVariantTranches -V {input.vcf} --resource {HAPMAP} --resource {MILLS} --info-key CNN_1D --snp-tranche {SNP_TRANCHE} --indel-tranche {INDEL_TRANCHE} --invalidate-previous-filters -O {output} -L {input.interval_list}"

rule var_germ_05_FilterNonpassingGermlineVariants:
    input: "out/WGS/variant_calling/{tumor_or_normal}/HTC-scattered/{sample}.HTC.{interval}.CNN-scored.tranched.vcf.gz"
    output: temp("out/WGS/variant_calling/{tumor_or_normal}/HTC-scattered/{sample}.HTC.{interval}.CNN-scored.tranched.filtered.vcf")
    params: n="1", R="'span[hosts=1] rusage[mem=4]'", \
        o="out/logs/filter_germline.out", eo="out/logs/filter_germline.err", \
        J="filter_germline"
    conda: "envs/bcftools.yaml"
    shell: "bcftools view -f PASS {input} > {output}"

rule var_germ_06_MergeIntervalWiseVCFs:
    input: expand("out/WGS/variant_calling/{{tumor_or_normal}}/HTC-scattered/{{sample}}.HTC.{interval}.CNN-scored.tranched.filtered.vcf",interval=[str(x).zfill(4) for x in range(NUM_VARIANT_INTERVALS)])
    output: "out/WGS/variant_calling/{tumor_or_normal}/{sample}.germline_finished.vcf"
    params: n="1", R="'span[hosts=1]'", \
        o="out/logs/merge_vcfs.out", eo="out/logs/merge_vcfs.err", \
        J="merge_vcfs"
    conda: "envs/gatk4.yaml"
    shell: "picard MergeVcfs $(echo '{input}' | sed -r 's/[^ ]+/I=&/g') O={output}"

rule var_germ_06b_ConsolidateSampleNamesForMerge:
    input: "out/WGS/variant_calling/{tumor_or_normal}/{sample}.germline_finished.vcf"
    output: temp("out/WGS/variant_calling/{tumor_or_normal}/{sample}.germline_finished.name_consolidated.vcf.gz"),name_txt=temp("out/WGS/variant_calling/{tumor_or_normal}/{sample}.cohort_name.txt")
    params: n="1", R="'span[hosts=1]'", \
        o="out/logs/consolidate_names.out", eo="out/logs/consolidate_names.err", \
        J="consolidate_names",int_vcf="out/WGS/variant_calling/{tumor_or_normal}/{sample}.germline_finished.name_consolidated.vcf"
    conda: "envs/bcftools.yaml"
    shell: "echo '{COHORT}_{wildcards.tumor_or_normal}' > {output.name_txt}; bcftools reheader -s {output.name_txt} {input} > {params.int_vcf}; bgzip {params.int_vcf}; tabix -p vcf {params.int_vcf}.gz"

rule var_germ_07t_CombineTumorSampleGermlineVCFs:
    input: expand("out/WGS/variant_calling/tumor/{sample}.germline_finished.name_consolidated.vcf.gz",sample=TUMOR_SAMPLES)
    output: "out/WGS/variant_calling/tumor/{cohort}.tumor.germline_finished.vcf.gz"
    params: n="1", R="'span[hosts=1]'", \
        o="out/logs/merge_tumor_vcfs.out", eo="out/logs/merge_tumor_vcfs.err", \
        J="merge_tumor_vcfs", int_vcf="out/WGS/variant_calling/tumor/{cohort}.tumor.germline_finished.vcf"
    conda: "envs/bcftools.yaml"
    shell: "bcftools concat -a -D {input} > {params.int_vcf}; bgzip {params.int_vcf}; tabix -p vcf {params.int_vcf}.gz"
    #shell: "picard MergeVcfs $(echo '{input}' | sed -r 's/[^ ]+/I=&/g') O={output}"

rule var_germ_07n_MergeNormalSampleGermlineVCFs:
    input: expand("out/WGS/variant_calling/normal/{sample}.germline_finished.vcf.gz",sample=NORMAL_SAMPLES)
    output: "out/WGS/variant_calling/normal/{cohort}.normal.germline_finished.vcf.gz"
    params: n="1", R="'span[hosts=1]'", \
        o="out/logs/merge_normal_vcfs.out", eo="out/logs/merge_normal_vcfs.err", \
        J="merge_normal_vcfs"
    conda: "envs/bcftools.yaml"
    shell: "bcftools concat -a -D {input} > {params.int_vcf}; bgzip {params.int_vcf}; tabix -p vcf {params.int_vcf}.gz"
    #shell: "picard MergeVcfs $(echo '{input}' | sed -r 's/[^ ]+/I=&/g') O={output}"


## PINDEL RULES ##

rule CreatePindelConfigFile:
    input: ANALYSIS_READY_BAMFILES
    output: "out/WGS/variant_calling/pindel/pindel_config_file.txt"
    params: n="1", R="'span[hosts=1]'", \
        o="out/logs/create_pindel_configfile.out", eo="out/logs/create_pindel_configfile.err", \
        J="pindel_config"
    run: 
        for sample in ALL_SAMPLES:
            bam_file = "out/WGS/variant_calling/tumor/{}.analysis_ready.bam".format(sample) if sample in TUMOR_SAMPLES else "out/WGS/variant_calling/normal/{}.analysis_ready.bam".format(sample)
            insert_length = config['input_files']['genome_personalization_module'][input_file_format+'_inputs'][sample]['insert_size']
            open(output[0],'a').write("{}\t{}\t{}\n".format(bam_file,insert_length,sample))

try:
    fa_index_file = open('{}.fai'.format(STOCK_GENOME_FASTA))
except FileNotFoundError:
    print("Genome FASTA is not indexed! Please run 'samtools faidx <FASTA>'.")
CHROMOSOMES = [x.split('\t')[0] for x in fa_index_file.readlines()]
rule CallLongIndelsAndSVsWithPindel:
    input: config="out/WGS/variant_calling/pindel/pindel_config_file.txt", ref_fasta=STOCK_GENOME_FASTA
    output: "out/WGS/variant_calling/pindel/scattered/{cohort}.{chr}.pindel"
    params: n="4", R="'span[hosts=1] rusage[mem=16]'", \
        o="out/logs/variant_calling/chr-wise/pindel_{chr}.out", eo="out/logs/variant_calling/chr-wise/pindel_{chr}.err", \
        J="pindel"
    conda: "envs/pindel.yaml"
    shell: "pindel -T {params.n} -f {input.ref_fasta} -i {input.config} -c {wildcards.chr} -o {output}"

rule Pindel2Vcf:
    input: pindel="out/WGS/variant_calling/pindel/scattered/{cohort}.{chr}.pindel_TD", ref_fasta=STOCK_GENOME_FASTA
    output: "out/WGS/variant_calling/pindel/scattered/{cohort}.{chr}.pindel_TD.vcf"
    params: n="4", R="'span[hosts=1] rusage[mem=16]'", \
        o="out/logs/variant_calling/chr-wise/pindel2vcf_{chr}.out", eo="out/logs/variant_calling/chr-wise/pindel2vcf_{chr}.err", \
        J="pindel2vcf"
    conda: "envs/pindel.yaml"
    shell: "pindel2vcf -T {params.n} -p {input.pindel} -r {input.ref_fasta} -R-c {wildcards.chr} -G"

## PINDEL development ongoing ##

## BEGIN Mutect2 RULES ##

GNOMAD_AF=config['parameters']['genome_personalization_module']['variant_calling']['resources']['somatic']['germline_population_db']
if NORMAL_SAMPLES is not None:
    rule var_som_01_Mutect2_matched_tumor_normal:
        input: tumor=expand("out/WGS/variant_calling/tumor/{sample}.analysis_ready.bam",sample=TUMOR_SAMPLES),normal=expand("out/WGS/variant_calling/normal/{sample}.analysis_ready.bam",sample=NORMAL_SAMPLES),ref=STOCK_GENOME_FASTA,interval_list="out/WGS/intervals/{interval}-scattered.interval_list",gnomad_af=GNOMAD_AF
        output: vcf=temp("out/WGS/variant_calling/tumor/Mutect2-scattered/{cohort}.mutect2.{interval}.vcf"),stats=temp("out/WGS/variant_calling/tumor/Mutect2-scattered/{cohort}.mutect2.{interval}.vcf.stats")
        params: n="8", R="'span[hosts=1] rusage[mem=4]'", \
            o="out/logs/variant_calling/intervals/mutect2_{interval}.out", eo="out/logs/variant_calling/intervals/mutect2_{interval}.err", \
            J="mutect2_matched"
        conda: "envs/gatk4.yaml"
        shell: "gatk --java-options '-Xmx32g' Mutect2 -R {input.ref} -O {output.vcf} \
                  $(echo '{input.tumor}' | sed -r 's/[^ ]+/-I &/g') \
                  $(echo '{input.normal}' | sed -r 's/[^ ]+/-I &/g') \
                  $(echo '{NORMAL_SAMPLES}' | sed -r 's/[^ ]+/-normal &/g') \
                  --germline-resource {input.gnomad_af} \
                  --native-pair-hmm-threads {params.n} \
                  -L {input.interval_list}"
else:
    rule var_som_01_Mutect2_without_matched_normal:
        input: tumor=expand("out/WGS/variant_calling/tumor/{sample}.analysis_ready.bam",sample=TUMOR_SAMPLES),ref=STOCK_GENOME_FASTA,interval_list="out/WGS/intervals/{interval}-scattered.interval_list",gnomad_af=GNOMAD_AF
        output: vcf="out/WGS/variant_calling/tumor/Mutect2-scattered/{cohort}..mutect2.{interval}.vcf",stats="out/WGS/variant_calling/cohort/Mutect2-scattered/{cohort}.mutect2.{interval}.vcf.stats"
        params: n="4", R="'span[hosts=1] rusage[mem=4]'", \
            o="out/logs/mutect2.out", eo="out/logs/mutect2.err", \
            J="mutect2_unmatched"
        conda: "envs/gatk4.yaml"
        shell: "gatk --java-options '-Xmx16g' Mutect2 -R {input.ref} -I {input.sample} -tumor {TUMOR_SAMPLES} --germline-resource {input.gnomad_af} -L {input.interval_list}"

rule var_som_02_MergeScatteredMutect2VCFs:
    input: vcf=expand("out/WGS/variant_calling/tumor/Mutect2-scattered/{{cohort}}.mutect2.{interval}.vcf",interval=[str(x).zfill(4) for x in range(NUM_VARIANT_INTERVALS)])
    output: "out/WGS/variant_calling/tumor/{cohort}.mutect2.vcf"
    params: n="1", R="'span[hosts=1] rusage[mem=8]'", \
            o="out/logs/merge_somatic.out", eo="out/logs/merge_somatic.err", \
            J="merge_somatic"
    conda: "envs/gatk4.yaml"
    shell: "picard MergeVcfs -Xmx8g \
              $(echo '{input.vcf}' | sed -r 's/[^ ]+/I=&/g') \
              O={output}"

rule var_som_02a_MergeScatteredMutect2Stats:
    input: stats=expand("out/WGS/variant_calling/tumor/Mutect2-scattered/{{cohort}}.mutect2.{interval}.vcf.stats",interval=[str(x).zfill(4) for x in range(NUM_VARIANT_INTERVALS)])
    output: "out/WGS/variant_calling/tumor/{cohort}.mutect2.vcf.stats"
    params: n="1", R="'span[hosts=1] rusage[mem=8]'", \
            o="out/logs/merge_mutect_stats.out", eo="out/logs/merge_mutect_stats.err", \
            J="merge_mutect_stats"
    conda: "envs/gatk4.yaml"
    shell: "gatk --java-options -Xmx8g MergeMutectStats -O {output} \
              $(echo '{input.stats}' | sed -r 's/[^ ]+/-stats &/g')"


rule var_som_00a_GetTumorPileupSummaries:
    input: tumor=expand("out/WGS/variant_calling/tumor/{sample}.analysis_ready.bam",sample=TUMOR_SAMPLES),gnomad_af=config['parameters']['genome_personalization_module']['variant_calling']['resources']['somatic']['germline_population_db'],intervals=config['parameters']['genome_personalization_module']['variant_calling']['resources']['wgs_calling_regions'],ref_fasta=STOCK_GENOME_FASTA
    output: "out/WGS/variant_calling/tumor/{cohort}_tumor.pileup_summaries.table"
    params: n="16", R="'span[hosts=1] rusage[mem=2]'", \
        o="out/logs/get_pileup_summaries.out", eo="out/logs/get_pileup_summaries.err", \
        J="get_pileup_summaries"
    conda: "envs/gatk4.yaml"
    shell: "gatk --java-options -Xmx32g GetPileupSummaries -R {input.ref_fasta} \
                $(echo '{input.tumor}' | sed -r 's/[^ ]+/-I &/g') \
                -V {input.gnomad_af} -L {input.intervals} -O {output}"

rule var_som_00b_CalculateContamination:
    input: "out/WGS/variant_calling/tumor/{cohort}_tumor.pileup_summaries.table"
    output: "out/WGS/variant_calling/tumor/{cohort}_tumor.contamination.table"
    params: n="4", R="'span[hosts=1] rusage[mem=8]'", \
        o="out/logs/calculate_contamination.out", eo="out/logs/calculate_contamination.err", \
        J="calculate_contamination"
    conda: "envs/gatk4.yaml"
    shell: "gatk --java-options -Xmx32g CalculateContamination -I {input} -O {output}"

rule var_som_03_ScoreVariantsWithFilterMutectCalls:
    input: vcf="out/WGS/variant_calling/tumor/{cohort}.mutect2.vcf",contam_table="out/WGS/variant_calling/tumor/{cohort}_tumor.contamination.table",stats="out/WGS/variant_calling/tumor/{cohort}.mutect2.vcf.stats",ref=STOCK_GENOME_FASTA
    output: "out/WGS/variant_calling/tumor/{cohort}.mutect2.scored.vcf.gz"
    params: n="1", R="'span[hosts=1] rusage[mem=16]'", \
        o="out/logs/filter_mutect2.out", eo="out/logs/filter_mutect2.err", \
        J="filter_mutect2"
    conda: "envs/gatk4.yaml"
    shell: "gatk --java-options -Xmx16g FilterMutectCalls -V {input.vcf} -R {input.ref} --contamination-table {input.contam_table} -stats {input.stats} -O {output}" 

rule var_som_04_FilterNonPassingSomaticVariants:
    input: "out/WGS/variant_calling/tumor/{cohort}.mutect2.scored.vcf.gz"
    output: "out/WGS/variant_calling/tumor/{cohort}.mutect2.scored.filtered.vcf"
    params: n="1", R="'span[hosts=1] rusage[mem=4]'", \
        o="out/logs/filter_somatic.out", eo="out/logs/filter_somatic.err", \
        J="filter_somatic"
    conda: "envs/bcftools.yaml"
    shell: "bcftools view -f PASS {input} > {output}"

rule var_som_05_SeparatePassingSomaticVariantsBySample:
    input: "out/WGS/variant_calling/tumor/{cohort}.mutect2.scored.filtered.vcf"
    output: expand("out/WGS/variant_calling/tumor/{{cohort}}.mutect2.scored.filtered.{sample}.vcf.gz",sample=TUMOR_SAMPLES)
    params: n="1", R="'span[hosts=1] rusage[mem=4]'", \
        o="out/logs/variant_calling/somatic_separate_bySample.out", eo="out/logs/somatic_separate_bySample.err", \
        J="somatic_filter+separate"
    conda: "envs/gatk4.yaml"
    shell: "for s in {TUMOR_SAMPLES}; do gatk --java-options -Xmx4g SelectVariants --sample-name $s --variant {input} --output out/WGS/variant_calling/tumor/{COHORT}.mutect2.scored.filtered.$s.vcf.gz; done"

"""
rule var_som_06_ConsolidateSampleNamesForMerge:
    input: "out/WGS/variant_calling/tumor/{cohort}.mutect2.scored.filtered.{sample}.vcf.gz"
    output: temp("out/WGS/variant_calling/tumor/{cohort}.mutect2.scored.filtered.{sample}.name_consolidated.vcf.gz"),name_txt=temp("out/WGS/variant_calling/tumor/{sample}.cohort_name.{cohort}.txt")
    params: n="1", R="'span[hosts=1]'", \
        o="out/logs/consolidate_names.out", eo="out/logs/consolidate_names.err", \
        J="consolidate_names",int_vcf="out/WGS/variant_calling/tumor/{cohort}.mutect2.scored.filtered.{sample}.name_consolidated.vcf"
    conda: "envs/bcftools.yaml"
    shell: "echo '{COHORT}_tumor' > {output.name_txt}; bcftools reheader -s {output.name_txt} {input} > {params.int_vcf}; bgzip {params.int_vcf}; tabix -p vcf {params.int_vcf}.gz"
"""
rule var_som_06_ConsolidateSampleNamesForMerge:
    input: "out/WGS/variant_calling/tumor/{cohort}.mutect2.scored.filtered.{sample}.vcf.gz"
    output: vcf=temp("out/WGS/variant_calling/tumor/{cohort}.mutect2.scored.filtered.{sample}.name_consolidated.vcf.gz"),name_txt=temp("out/WGS/variant_calling/tumor/{sample}.cohort_name.{cohort}.txt"),idx=temp("out/WGS/variant_calling/tumor/{cohort}.mutect2.scored.filtered.{sample}.name_consolidated.vcf.gz.tbi")
    params: n="1", R="'span[hosts=1]'", \
        o="out/logs/consolidate_names.out", eo="out/logs/consolidate_names.err", \
        J="consolidate_names",int_vcf="out/WGS/variant_calling/tumor/{cohort}.mutect2.scored.filtered.{sample}.name_consolidated.vcf"
    conda: "envs/bcftools.yaml"
    shell: "echo '{COHORT}_tumor' > {output.name_txt}; bcftools reheader -s {output.name_txt} {input} > {output.vcf}; tabix -p vcf {output.vcf}"

rule var_som_07_CombineSomaticVCFs:
    input: vcf=expand("out/WGS/variant_calling/tumor/{{cohort}}.mutect2.scored.filtered.{sample}.name_consolidated.vcf.gz",sample=TUMOR_SAMPLES),idx=expand("out/WGS/variant_calling/tumor/{{cohort}}.mutect2.scored.filtered.{sample}.name_consolidated.vcf.gz.tbi",sample=TUMOR_SAMPLES)
    output: "out/WGS/variant_calling/tumor/{cohort}.somatic_finished.vcf.gz"
    params: n="1", R="'span[hosts=1]'", \
        o="out/logs/merge_tumor_vcfs.out", eo="out/logs/merge_tumor_vcfs.err", \
        J="merge_tumor_vcfs", int_vcf="out/WGS/variant_calling/tumor/{cohort}.somatic_finished.vcf"
    conda: "envs/bcftools.yaml"
    shell: "bcftools concat -a -D {input.vcf} > {params.int_vcf}; bgzip {params.int_vcf}; tabix -p vcf {params.int_vcf}.gz"

"""
rule var_som_05_ReformatMutectVCF:
    input: "out/WGS/variant_calling/tumor/{cohort}.mutect2.filtered.vcf"
    output: "out/WGS/variant_calling/tumor/{cohort}.somatic_finished.vcf"
    params: n="1", R="'span[hosts=1] rusage[mem=8]'", \
            o="out/logs/reformat_mutect_vcf.out", eo="out/logs/reformat_mutect_vcf.err", \
            J="reformat_mutect_vcf"
    run:
        vcf = open(input[0]).readlines()
        for line in vcf:
            if '\t' not in line: open(output[0],'a').write(line)
            else:
                tsv = line.split('\t')
                tsv = tsv[0:len(tsv)-2] + [tsv[len(tsv)-1]]
                open(output[0],'a').write('\t'.join(tsv))
"""

rule var_z_MergeFinishedTumorVCFs:
    input: ["out/WGS/variant_calling/tumor/{cohort}.somatic_finished.vcf.gz","out/WGS/variant_calling/tumor/{cohort}.tumor.germline_finished.vcf.gz"]
    output: "out/WGS/variant_calling/tumor/{cohort}.tumor.variant_calling_finished.vcf.gz"
    params: n="1", R="'span[hosts=1] rusage[mem=8]'", \
            o="out/logs/merge_finished_vcfs.out", eo="out/logs/merge_finished_vcfs.err", \
            J="merge_finished_vcfs"
    conda: "envs/gatk4.yaml"
    shell: "picard MergeVcfs $(echo '{input}' | sed -r 's/[^ ]+/I=&/g') O={output}"

"""
rule var_z_FinishedNormalVCF:
    input: "out/WGS/variant_calling/normal/normal.germline_finished.vcf.gz"
    output: "out/WGS/variant_calling/cohort/{cohort}.normal.variant_calling_finished.vcf.gz"
    params: n="1", R="'span[hosts=1]'", \
            o="out/logs/merge_finished_vcfs.out", eo="out/logs/merge_finished_vcfs.err", \
            J="merge_finished_vcfs"
    run:
        in_path = os.path.abspath(input[0])
        out_path = os.path.abspath(output[0])
        command = "ln -s {} {}".format(in_path, out_path)
        shell(command)
"""
