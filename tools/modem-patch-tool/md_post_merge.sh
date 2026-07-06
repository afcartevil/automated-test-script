#!/bin/bash

NODE_BRANCH=
target_BRANCH=
AP_lable=
DESCRIPTION=基线升级
JIRAID=

TARGET_BEFORE_COMMIT_FILE=.git/.md_merge_target_before_commit_id

function post_merge()
{
    if [ -d tools/ ]; then
        echo location is right, keep build
    else
        cd ..
    fi

    if [ ! -d log/ ]; then
        mkdir -p log/
    fi

    target_before_commit_id=
    if [ -f ${TARGET_BEFORE_COMMIT_FILE} ]; then
        target_before_commit_id=$(cat ${TARGET_BEFORE_COMMIT_FILE} | tail -n 1)
    fi
    if [ -z ${target_before_commit_id} ]; then
        target_before_commit_id=$(git rev-parse HEAD^1)
    fi

    current_commit_id=$(git rev-parse HEAD)

    git diff --name-only ${target_before_commit_id} ${current_commit_id} >> log/merge_file.log
    git diff ${target_before_commit_id} ${current_commit_id} >> log/product.diff
    diff log/node.diff log/product.diff >> log/compare.diff

    if [ -d "projects/" ]; then
        echo projects exist | tee -a log/md_build.log
    else
        echo find projects fail, projects is not exist !!! | tee -a log/md_build.log
        exit 0
    fi

    check_result=false
    : > log/file_conflict_check.log
    for projects in $(ls projects/)
    do
        echo projects = ${projects} >> log/md_build.log
        echo -e "\033[32m  ====================================\033[0m" | tee -a log/file_conflict_check.log
        echo "projects = ${projects}" | tee -a log/file_conflict_check.log
        if [ -d projects/${projects} ]; then
            for file in $(cat log/merge_file.log)
            do
                file_path=projects/${projects}/${file}
                echo check file_path ${file_path} >> log/md_build.log
                if [ -f ${file_path} ]; then
                    echo conflict_file_path:${file_path} | tee -a log/file_conflict_check.log
                    check_result=true
                fi
            done
        fi
    done

    echo check_result = ${check_result} | tee -a log/md_build.log
    if [ ${check_result} != "true" ]; then
        echo "successful, patch修改与客制化差异文件无冲突！！！" | tee -a log/md_build.log
    else
        echo "fail, patch修改与客制化差异文件冲突，请owner检查！！！" | tee -a log/md_build.log
    fi

    git add --all
    git reset -- tools/md_merge_noninteractive.sh tools/md_post_merge.sh tools/md_continue_after_conflict.sh tools/apm_refresh_conflicts.sh 2>/dev/null || true
    git commit --amend -m "ID: ${JIRAID}
DESCRIPTION: MTK Patch ${AP_lable} ${DESCRIPTION}
TYPE:patch
AFFECT_PROJECTS:ALL
TEST_SUGGESTIONS:basic test" | tee -a log/merge_conflict.log
    amend_rc=${PIPESTATUS[0]}
    if [ ${amend_rc} -ne 0 ]; then
        echo "git commit --amend failed" | tee -a log/md_build.log
        exit 1
    fi

    echo "skip git push for local debug" | tee -a log/md_build.log
    push_rc=0
    if command -v timeout >/dev/null 2>&1; then
        # GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=15" timeout 600 git push --no-thin origin HEAD:refs/for/${target_BRANCH} 2>&1 | tee -a log/md_build.log
        :
    else
        # GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=15" git push --no-thin origin HEAD:refs/for/${target_BRANCH} 2>&1 | tee -a log/md_build.log
        :
    fi
    if [ ${push_rc} -ne 0 ]; then
        echo "git push failed" | tee -a log/md_build.log
        exit 1
    fi

    git merge --quit >/dev/null 2>&1 || true

    rm -f ${TARGET_BEFORE_COMMIT_FILE}
    rm -f tools/md_merge_noninteractive.sh tools/md_post_merge.sh tools/md_continue_after_conflict.sh tools/apm_refresh_conflicts.sh 2>/dev/null || true
}

post_merge
