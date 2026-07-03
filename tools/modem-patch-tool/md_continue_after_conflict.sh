#!/bin/bash

NODE_BRANCH=
target_BRANCH=
AP_lable=
DESCRIPTION=基线升级
JIRAID=

function continue_after_conflict()
{
    if [ -d tools/ ]; then
        echo location is right, keep build
    else
        cd ..
    fi

    if [ ! -d log/ ]; then
        mkdir -p log/
    fi

    if [ ! -f .git/MERGE_HEAD ]; then
        echo "MERGE_HEAD not found, not in merge state" | tee -a log/md_build.log
        bash tools/md_post_merge.sh
        exit $?
    fi

    unmerged=$(GIT_PAGER=cat git diff --name-only --diff-filter=U)
    if [ -n "${unmerged}" ]; then
        echo "Detecting conflict markers in unmerged files..." | tee -a log/md_build.log
        git grep -n '^<<<<<<<' -- $(echo "${unmerged}" | tr '\n' ' ') >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            echo "Conflict markers remain (<<<<<<<) in unmerged files" | tee -a log/md_build.log
            echo "${unmerged}" | tee -a log/md_build.log
            exit 2
        fi
    fi

    echo "Auto staging resolved files (git add --all)..." | tee -a log/md_build.log
    git add --all
    git reset -- tools/md_merge_noninteractive.sh tools/md_post_merge.sh tools/md_continue_after_conflict.sh tools/apm_refresh_conflicts.sh 2>/dev/null || true

    unmerged_after_add=$(GIT_PAGER=cat git diff --name-only --diff-filter=U)
    if [ -n "${unmerged_after_add}" ]; then
        echo "Unmerged files remain after git add:" | tee -a log/md_build.log
        echo "${unmerged_after_add}" | tee -a log/md_build.log
        exit 2
    fi

    if [ -n "${unmerged}" ]; then
        git grep --cached -n '^<<<<<<<' -- $(echo "${unmerged}" | tr '\n' ' ') >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            echo "Conflict markers remain in index (cached)" | tee -a log/md_build.log
            exit 2
        fi
    fi

    echo "第 1 次输入" | tee -a log/md_build.log
    echo "line_result = y" | tee -a log/md_build.log

    git commit -m "ID: ${JIRAID}
DESCRIPTION: MTK Patch ${AP_lable} ${DESCRIPTION}
TYPE:patch
AFFECT_PROJECTS:ALL
TEST_SUGGESTIONS:basic test" | tee -a log/merge_conflict.log
    commit_rc=${PIPESTATUS[0]}
    if [ ${commit_rc} -ne 0 ]; then
        echo "git commit failed" | tee -a log/md_build.log
        exit 1
    fi

    git merge --quit >/dev/null 2>&1 || true

    bash tools/md_post_merge.sh
}

continue_after_conflict
