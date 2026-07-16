#!/bin/bash

NODE_BRANCH=
NODE_REF=
target_BRANCH=
AP_lable=
DESCRIPTION=基线升级
JIRAID=
before_node_commit_id=

PATCH_NUM=
PATCH_ID=MOLY########
PATCH_LEN=2
PATCH_PATH=$1
MODEM_SOURCE_PATH=$(pwd)
MD_COMMIT_TEMPLATE=.commit.template
TARGET_BEFORE_COMMIT_FILE=.git/.md_merge_target_before_commit_id

function target_merge()
{
    if [ -d tools/ ]; then
        echo location is right, keep build
    else
        cd ..
    fi

    current_branch=$(git rev-parse --abbrev-ref HEAD)
    git clean -xdf
    git checkout .

    echo change current_node_branch ${current_branch} | tee -a md_build.log
    echo NODE_BRANCH ${NODE_BRANCH} | tee -a md_build.log
    echo NODE_REF ${NODE_REF} | tee -a md_build.log
    node_commit_id=$(git rev-parse ${NODE_REF})
    if [ -z "${node_commit_id}" ]; then
        echo -e "\033[32m resolve NODE_REF ${NODE_REF} fail !!! \033[0m" | tee -a md_build.log
        exit 1
    fi
    echo node_commit_id ${node_commit_id} | tee -a md_build.log
    git diff ${before_node_commit_id} ${node_commit_id} >> node.diff

    git checkout ${target_BRANCH}

    rm -rf log/
    mkdir log/
    : > log/merge_conflict.log
    : > log/merge_file.log
    : > log/product.diff
    : > log/compare.diff
    : > log/file_conflict_check.log
    cp md_build.log log/
    cp node.diff log/
    rm -rf md_build.log node.diff

    current_branch=$(git rev-parse --abbrev-ref HEAD)

    echo change current_target_branch ${current_branch} | tee -a log/md_build.log
    if [ "${current_branch}" == "${target_BRANCH}" ]; then
        target_before_commit_id=$(git rev-parse HEAD)
        echo ${target_before_commit_id} > ${TARGET_BEFORE_COMMIT_FILE}
        git merge --no-progress ${NODE_REF} -m "ID: ${JIRAID}
DESCRIPTION: MTK Patch ${AP_lable} ${DESCRIPTION}
TYPE:patch
AFFECT_PROJECTS:ALL
TEST_SUGGESTIONS:basic test" | tee -a log/merge_conflict.log
    else
        echo -e "\033[32m checkout target_BRANCH ${target_BRANCH} fail !!!\033[0m" | tee -a log/md_build.log
        exit 0
    fi

    current_commit_id=$(git rev-parse HEAD)
    if [ "${current_commit_id}" != "${target_before_commit_id}" ]; then
        merge_result=$(grep "Automatic merge failed" log/merge_conflict.log)
        if [ -z "${merge_result}" ];then
            echo -e "\033[31m git merge PASS !!!\033[0m" | tee -a log/md_build.log
        else
            echo -e "\033[32m git merge fail !!!\033[0m" | tee -a log/md_build.log
            echo node_commit_id = ${node_commit_id}  | tee -a log/md_build.log
            echo target_before_commit_id = ${target_before_commit_id}  | tee -a log/md_build.log
            echo current_commit_id = ${current_commit_id}  | tee -a log/md_build.log
            echo please check log/merge_conflict.log  | tee -a log/md_build.log
            echo if you resolve this merge conflict,please ENTER y | tee -a log/md_build.log
            exit 1
        fi
    else
        echo -e "\033[32m git merge fail !!!\033[0m" | tee -a log/md_build.log
        echo node_commit_id = ${node_commit_id}  | tee -a log/md_build.log
        echo target_before_commit_id = ${target_before_commit_id}  | tee -a log/md_build.log
        echo current_commit_id = ${current_commit_id}  | tee -a log/md_build.log
        echo please check log/merge_conflict.log  | tee -a log/md_build.log
        echo if you resolve this merge conflict,please ENTER y | tee -a log/md_build.log
        exit 1
    fi
}

function main()
{
    target_merge
}

main $1
