# Initialize home/working/output directories
WD = config['directories']['working_and_output_dir']
workdir: WD
PG2_HOME=config['directories']['PG2_installation_dir']
TMP_DIR=config['directories']['optional']['temp_dir']

# Initialize stock references
STOCK_GENOME_FASTA=config['stock_references']['genome']['fasta']
STOCK_GENOME_GTF=config['stock_references']['genome']['gtf']

# Cohort/Organism info
COHORT=config['input_files']['genome_personalization_module']['cohort_or_organism_name']


input_file_format = config['input_files']['genome_personalization_module']['input_file_format']

if 'vcf' in input_file_format:
    INPUT_VCFS = config['input_files']['genome_personalization_module']['vcf_inputs'].keys()
    INPUT_VCF_GZ_FILES = [config['input_files']['genome_personalization_module']['vcf_inputs'][x]['vcf.gz_file'] for x in INPUT_VCFS]
    
    input_vcf_aligned_fastas = [config['input_files']['genome_personalization_module']['vcf_inputs'][x]['aligned_genome']['fasta'] for x in INPUT_VCFS]
    for fa in input_vcf_aligned_fastas:
        assert(fa == STOCK_GENOME_FASTA), "Error: At least one of your input vcfs is aligned to a different reference genome than the provided stock ref genome.\n\
            Please use UCSC liftOver or CrossMap to realign each vcf's genome coordinates with the provided stock ref genome, or recreate them using the correct reference genome."


# To run genome personalization, one of the following 3 conditions must be met:

# 1) (If fresh PG2 run) either germline and/or somatic variants are being called
calling_variants = config['user_defined_workflow']['genome_personalization_module']['variant_calling_submodule']['call_germline_variants_with_GATK4_HaplotypeCaller'] or config['user_defined_workflow']['genome_personalization_module']['variant_calling_submodule']['if_inputs_are_matched_tumor-normal_samples']['call_somatic_variants_with_GATK4_Mutect2']

# 2) (If continuing/re-running a previous PG2 run) either germline and/or somatic variants HAVE been called by PG2, and the corresponding output filenames/directories have not been changed
just_called_variants = config['user_defined_workflow']['genome_personalization_module']['variant_calling_submodule']['continuation']['just_finished_variant_calling']

# 3) User supplies externally called VCF(s) as inputs 
if not (calling_variants or just_called_variants): assert 'vcf' in input_file_format, "in order to run genome personalization, you must either call variants on WGS/WES input data, or supply a called VCF."


try:
    fa_index_file = open('{}.fai'.format(STOCK_GENOME_FASTA))
except FileNotFoundError:
    print("Genome FASTA is not indexed! Please run 'samtools faidx <FASTA>'.")

CHROMOSOMES = [x.split('\t')[0] for x in fa_index_file.readlines()]
HAPLOTYPES = [1,2] if config['parameters']['genome_personalization_module']['variant_calling']['make_customRef_diploid'] else [1]

rule all:
    input: expand("out/custom_ref/{cohort}_H{htype}.fa",cohort=COHORT,htype=HAPLOTYPES), expand("out/custom_ref/{cohort}_H{htype}.chain",cohort=COHORT,htype=HAPLOTYPES), expand("out/custom_ref/{cohort}_H{htype}.gtf",cohort=COHORT,htype=HAPLOTYPES)


snakemake.utils.makedirs('out/logs/chr-wise')
snakemake.utils.makedirs('out/logs/custom_ref')


subworkflow WGS_variant_calling:
    snakefile: "WGS_variant_calling.py"
    configfile: workflow.overwrite_configfile
    workdir: WD

# For each chromosome, patch the stock reference with variants contained in the (phased) VCF.
if (not just_called_variants) and calling_variants:
    rule genome_01_CreateChrWiseCustomRef:
        input: vcf=WGS_variant_calling("out/{study_group}/variant_calling/{cohort}.{study_group}.variant_calling_finished.vcf.gz")
        output: fasta=temp("out/custom_ref/chr_split/{study_group}/{cohort}.h-{htype}^{chr}.fa"),chain=temp("out/custom_ref/chr_split/{study_group}/{cohort}.h-{htype}^{chr}.chain")
        params: n="1", mem_per_cpu="4", R="'rusage[mem=4]'", J="chr-wise_customRef", o="out/logs/chr-wise/{study_group}.{htype}^{chr}.out", eo="out/logs/chr-wise/{study_group}.{htype}^{chr}.err", \
                study_grp=COHORT+'_{study_group}'
        # conda: "envs/bcftools.yaml"
        singularity: 'docker://pegi3s/samtools_bcftools:latest',
        shell: "samtools faidx {STOCK_GENOME_FASTA} {wildcards.chr} | bcftools consensus -s {params.study_grp} -H {wildcards.htype} -p {wildcards.htype}_ -c {output.chain} {input.vcf} > {output.fasta}"
elif just_called_variants:
    rule genome_01_CreateChrWiseCustomRef:
        input: vcf="out/{study_group}/variant_calling/{cohort}.{study_group}.variant_calling_finished.vcf.gz"
        output: fasta=temp("out/custom_ref/chr_split/{study_group}/{cohort}.h-{htype}^{chr}.fa"),chain=temp("out/custom_ref/chr_split/{study_group}/{cohort}.h-{htype}^{chr}.chain")
        params: n="1", mem_per_cpu="4", R="'rusage[mem=4]'", J="chr-wise_customRef", o="out/logs/chr-wise/{study_group}.{htype}^{chr}.out", eo="out/logs/chr-wise/{study_group}.{htype}^{chr}.err", \
                study_grp=COHORT+'_{study_group}'
        # conda: "envs/bcftools.yaml"
        singularity: 'docker://pegi3s/samtools_bcftools:latest',
        shell: "samtools faidx {STOCK_GENOME_FASTA} {wildcards.chr} | bcftools consensus -s {params.study_grp} -H {wildcards.htype} -p {wildcards.htype}_ -c {output.chain} {input.vcf} > {output.fasta}"
else:
    #TODO: implement tumor/matched normal functionality via sample name changes
    rule genome_00_MergeAllInputVCFs:
        input: vcfs=INPUT_VCF_GZ_FILES
        output: merged_vcf="out/WGS/{cohort}.input_vcfs_merged.vcf.gz"
        #conda: "envs/myenv.yaml"
        params: n="1", mem_per_cpu="6", R="'rusage[mem=6]'", J="merge_input_vcfs", o="out/logs/merge_input_vcfs.out", eo="out/logs/merge_input_vcfs.err"
        # conda: "envs/bcftools.yaml"
        singularity: "docker://broadinstitute/gatk"
        shell: "gatk --java-options '-Xmx6g' MergeVcfs \
            $(echo {input.vcfs} | sed -r 's/[^ ]+/-I &/g') \
            -O {output.merged_vcf}"
    rule genome_01_CreateChrWiseCustomRef:
        input: merged_vcf="out/WGS/{cohort}.input_vcfs_merged.vcf.gz"
        output: fasta=temp("out/custom_ref/chr_split/{study_group}/{cohort}.h-{htype}^{chr}.fa"),chain=temp("out/custom_ref/chr_split/{study_group}/{cohort}.h-{htype}^{chr}.chain")
        # conda: "envs/bcftools.yaml"
        singularity: 'docker://pegi3s/samtools_bcftools:latest',
        params: n="1", mem_per_cpu="4", R="'rusage[mem=4]'", J="chr-wise_customRef", o="out/logs/chr-wise/{study_group}.{htype}^{chr}.out", eo="out/logs/chr-wise/{study_group}.{htype}^{chr}.err",study_grp=COHORT+'_{study_group}'
        shell: "samtools faidx {STOCK_GENOME_FASTA} {wildcards.chr} | bcftools consensus -s {params.study_grp} -H {wildcards.htype} -p {wildcards.htype}_ -c {output.chain} {input.merged_vcf} > {output.fasta}"

# Reconstitute each newly individualized haplotype's complete sequence by merging all chromosomes of that haplotype
rule genome_02a_MergeChrWiseCustomRef:
    input: expand("out/custom_ref/chr_split/{{study_group}}/{{cohort}}.h-{{htype}}^{chr}.fa",chr=CHROMOSOMES),expand("out/custom_ref/chr_split/{{study_group}}/{{cohort}}.h-{{htype}}^{chr}.chain",chr=CHROMOSOMES)
    output: fasta="out/custom_ref/{cohort}.{study_group}.H{htype}.fa",chain="out/custom_ref/{cohort}.{study_group}.H{htype}.chain"
    params: n="1", mem_per_cpu="4", R="'rusage[mem=4]'", J="merge_customRef", o="out/logs/merge_customRef.out", eo="out/logs/merge_customRef.err"
    shell: "awk 1 out/custom_ref/chr_split/{wildcards.study_group}/{wildcards.cohort}.h-{wildcards.htype}^*.fa > {output.fasta}; awk 1 out/custom_ref/chr_split/{wildcards.study_group}/{wildcards.cohort}.h-{wildcards.htype}^*.chain > {output.chain}"

# Adjust genome annotation coords from reference to custom genome
# *** NOTE: this step incurs some data loss ***
rule genome_02b_LiftoverAnnotationGTF:
    input: chain="out/custom_ref/{cohort}.{study_group}.H{htype}.chain", vcf_refGtf=STOCK_GENOME_GTF
    output: "out/custom_ref/{cohort}.{study_group}.H{htype}.gtf"
    params: n="1", mem_per_cpu="4", R="'rusage[mem=4]'", J="LiftoverGTF", o="out/logs/liftover.out", eo="out/logs/liftover.err", \
            temp_gtf="out/custom_ref/{cohort}.{study_group}.H{htype}_temp.gtf"
    # conda: "envs/crossmap.yaml"
    singularity: 'docker://crukcibioinformatics/crossmap:latest'
    shell: "CrossMap.py gff {input.chain} {input.vcf_refGtf} {params.temp_gtf}; awk '{{print \"{wildcards.htype}_\" $0}}' {params.temp_gtf} > {output}; rm {params.temp_gtf}"

rule CreateRefSequenceIndex:
    input: STOCK_GENOME_FASTA
    output: STOCK_GENOME_FASTA+".fai"
    params: n="1", mem_per_cpu="18", R="'span[hosts=1] rusage[mem=18]'", o="out/logs/create_refIdx.out", eo="out/logs/create_refDict.err", J="create_refIdx"
    # conda: "envs/bcftools.yaml"
    singularity: 'docker://pegi3s/samtools_bcftools:latest',
    shell: "samtools faidx {input}"

rule CreateRefSequenceDict:
    input: STOCK_GENOME_FASTA
    output: STOCK_GENOME_FASTA.strip('fa')+'dict'
    params: n="1", mem_per_cpu="18", R="'span[hosts=1] rusage[mem=18]'", o="out/logs/create_refDict.out", eo="out/logs/create_refDict.err", J="create_refDict"
    # conda: "envs/bcftools.yaml"
    singularity: "docker://broadinstitute/gatk"
    shell: "gatk --java-options '-Xmx16g' CreateSequenceDictionary -R {input} -O {output}"
