#!/usr/bin/env bash

set -u
set -o pipefail

########################################
# basic config
########################################
SCRIPT_NAME="$(basename "$0")"
ROOT_DIR="$(pwd)"
SYSTEM_DIR=""
VENDOR_DIR=""
# trsys 根目录（入参 NEW_TRSYSTEM_ROOT）。打包时拼成 ${TRSYS_ROOT_DIR}/code/out_trsys/target
# 留空：含 trsys target 时在脚本 cwd 走 pipe_main。
TRSYS_ROOT_DIR=""
TRSYS_OUT_REL="code/out_trsys/target"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
STATUS_DIR="${ROOT_DIR}/.build_status_${TIMESTAMP}"
KEEPALIVE_INTERVAL=15

mkdir -p "${STATUS_DIR}"

########################################
# color
########################################
COLOR_GREEN="\033[32m"
COLOR_RED="\033[31m"
COLOR_RESET="\033[0m"

########################################
# usage
########################################
usage() {
    cat <<EOF
Usage:
  ${SCRIPT_NAME} <project> <build_varient> <build_flag> <build_target> <system_dir> <vendor_dir> [trsys_root_dir] [sys_version]

Args:
  project         project name
  build_varient   one of: user | user_root | userdebug
  build_flag      one of: bleeding_edge | staging | fooding | stable
  build_target    one or more of:
                  sys,krn,vext,hal,odm,trsys,pack
                  support both:
                  - sys,krn,hal,pack
                  - "sys krn hal pack"
  system_dir      Linux path to system tree
  vendor_dir      Linux path to vendor tree
  trsys_root_dir  optional Linux path to trsys root (TRSYS_ROOT_DIR)
  sys_version     optional; if omitted, sys build does not pass --version

Examples:
  ${SCRIPT_NAME} p1 userdebug staging sys /work/code/\$USER/sys /work/code/\$USER/vnd
  ${SCRIPT_NAME} p1 userdebug staging sys /work/code/\$USER/sys /work/code/\$USER/vnd /work/code/\$USER/trsys 16.4.0
  ${SCRIPT_NAME} p1 user stable sys,krn,hal,pack /work/code/\$USER/sys /work/code/\$USER/vnd
  ${SCRIPT_NAME} p1 user_root fooding "sys krn vext odm pack" /work/code/\$USER/sys /work/code/\$USER/vnd
  ${SCRIPT_NAME} p1 userdebug fooding "sys krn vext hal odm trsys pack" /work/code/\$USER/sys /work/code/\$USER/vnd /work/code/\$USER/trsys
EOF
}

########################################
# log helpers
########################################
log_info() {
    echo -e "${COLOR_GREEN}[$(date '+%F %T')] [INFO] $*${COLOR_RESET}"
}

log_error() {
    echo -e "${COLOR_RED}[$(date '+%F %T')] [ERROR] $*${COLOR_RESET}" >&2
}

########################################
# pipe_main (trsys)
########################################
invoke_pipe_main() {
    if command -v pipe_main >/dev/null 2>&1; then
        pipe_main "$@"
    elif [[ -f /opt/ci/rdtool/pipe_main ]]; then
        /opt/ci/civenv/bin/python3 /opt/ci/rdtool/pipe_main "$@"
    else
        echo "[ERROR] pipe_main not found in PATH and /opt/ci/rdtool/pipe_main missing" >&2
        return 127
    fi
}

########################################
# time helpers
########################################
now_epoch() {
    date '+%s'
}

format_duration() {
    local total_sec="$1"
    local h m s
    h=$((total_sec / 3600))
    m=$(((total_sec % 3600) / 60))
    s=$((total_sec % 60))
    printf "%02dh:%02dm:%02ds" "${h}" "${m}" "${s}"
}

########################################
# parse args
########################################
if [[ $# -lt 6 || $# -gt 8 ]]; then
    usage
    exit 1
fi

PROJECT="$1"
BUILD_VARIENT="$2"
BUILD_FLAG="$3"
BUILD_TARGET_RAW="$4"
SYSTEM_DIR="$5"
VENDOR_DIR="$6"
TRSYS_ROOT_DIR="${7:-}"
SYS_VERSION="${8:-}"

PREPARE_LOG="${ROOT_DIR}/${PROJECT}_prepare_${TIMESTAMP}.log"

case "${BUILD_VARIENT}" in
    user|user_root|userdebug)
        ;;
    *)
        log_error "invalid build_varient: ${BUILD_VARIENT}"
        log_error "allowed: user | user_root | userdebug"
        exit 1
        ;;
esac

case "${BUILD_FLAG}" in
    bleeding_edge|staging|fooding|stable)
        ;;
    *)
        log_error "invalid build_flag: ${BUILD_FLAG}"
        log_error "allowed: bleeding_edge | staging | fooding | stable"
        exit 1
        ;;
esac

TARGET_STR="$(echo "${BUILD_TARGET_RAW}" | tr ',' ' ' | xargs)"

if [[ -z "${TARGET_STR}" ]]; then
    log_error "build_target is empty"
    exit 1
fi

declare -a TARGETS=()
declare -A TARGET_SEEN=()

for t in ${TARGET_STR}; do
    case "${t}" in
        sys|krn|vext|hal|odm|trsys|pack)
            if [[ -z "${TARGET_SEEN[$t]+x}" ]]; then
                TARGETS+=("${t}")
                TARGET_SEEN["$t"]=1
            fi
            ;;
        *)
            log_error "invalid build_target: ${t}"
            log_error "allowed: sys | krn | vext | hal | odm | trsys | pack"
            exit 1
            ;;
    esac
done

NEED_SYSTEM_DIR=0
for t in "${TARGETS[@]}"; do
    if [[ "${t}" == "sys" || "${t}" == "pack" ]]; then
        NEED_SYSTEM_DIR=1
        break
    fi
done
if [[ ${NEED_SYSTEM_DIR} -eq 1 ]]; then
    if [[ ! -d "${SYSTEM_DIR}" ]]; then
        log_error "system directory not found: ${SYSTEM_DIR}"
        exit 1
    fi
fi
if [[ ! -d "${VENDOR_DIR}" ]]; then
    log_error "vendor directory not found: ${VENDOR_DIR}"
    exit 1
fi

########################################
# project config path
########################################
PROJECT_DIR="${VENDOR_DIR}/vendor/transsion/projects/${PROJECT}"
FULL_MK="${PROJECT_DIR}/full_${PROJECT}.mk"
VND_MK="${PROJECT_DIR}/vnd_${PROJECT}.mk"
ODM_MK="${PROJECT_DIR}/odm_${PROJECT}.mk"

if [[ ! -d "${PROJECT_DIR}" ]]; then
    log_error "project dir not found: ${PROJECT_DIR}"
    exit 1
fi

if [[ ! -f "${FULL_MK}" ]]; then
    log_error "file not found: ${FULL_MK}"
    exit 1
fi

if [[ ! -f "${VND_MK}" ]]; then
    log_error "file not found: ${VND_MK}"
    exit 1
fi

if [[ ! -f "${ODM_MK}" ]]; then
    log_error "file not found: ${ODM_MK}"
    exit 1
fi

########################################
# parse macro helper
########################################
parse_mk_var() {
    local file="$1"
    local key="$2"

    awk -v k="$key" '
    BEGIN { found=0 }
    {
        line=$0
        sub(/^[[:space:]]+/, "", line)
        if (line ~ /^#/) next

        if (line ~ ("^export[[:space:]]+" k "[[:space:]]*[:]?=")) {
            sub("^export[[:space:]]+" k "[[:space:]]*[:]?=[[:space:]]*", "", line)
            print line
            found=1
            exit
        }
        if (line ~ ("^" k "[[:space:]]*[:]?=")) {
            sub("^" k "[[:space:]]*[:]?=[[:space:]]*", "", line)
            print line
            found=1
            exit
        }
    }
    END {
        if (found == 0) exit 1
    }' "${file}" | sed 's/[[:space:]]*$//'
}

PROJECT_SYS="$(parse_mk_var "${FULL_MK}" "SYS_TARGET_PROJECT")" || {
    log_error "failed to parse SYS_TARGET_PROJECT from ${FULL_MK}"
    exit 1
}

PROJECT_HAL="$(parse_mk_var "${VND_MK}" "HAL_TARGET_PROJECT")" || {
    log_error "failed to parse HAL_TARGET_PROJECT from ${VND_MK}"
    exit 1
}

PROJECT_KRN="$(parse_mk_var "${VND_MK}" "KRN_TARGET_PROJECT")" || {
    log_error "failed to parse KRN_TARGET_PROJECT from ${VND_MK}"
    exit 1
}

PROJECT_VEXT="$(parse_mk_var "${VND_MK}" "VEXT_TARGET_PROJECT")" || {
    log_error "failed to parse VEXT_TARGET_PROJECT from ${VND_MK}"
    exit 1
}

PROJECT_ODM="$(parse_mk_var "${ODM_MK}" "VEXT_TARGET_PROJECT")" || {
    log_error "failed to parse VEXT_TARGET_PROJECT from ${ODM_MK}"
    exit 1
}

########################################
# resolve trsys_dir
########################################
HAS_TRSYS_TARGET=0
if [[ -n "${TARGET_SEEN[trsys]+x}" ]]; then
    HAS_TRSYS_TARGET=1
fi

# NEW_TRSYSTEM_ROOT 有值：打包用 ${TRSYS_ROOT_DIR}/code/out_trsys/target
# NEW_TRSYSTEM_ROOT 为空且含 trsys：在脚本 cwd（ea-build）走 pipe_main
TRSYS_WORKDIR=""
if [[ ${HAS_TRSYS_TARGET} -eq 1 ]]; then
    if [[ -n "${TRSYS_ROOT_DIR}" ]]; then
        if [[ ! -d "${TRSYS_ROOT_DIR}" ]]; then
            log_error "trsys root directory not found: ${TRSYS_ROOT_DIR}"
            exit 1
        fi
        TRSYS_WORKDIR="${TRSYS_ROOT_DIR}"
        TRSYS_DIR="${TRSYS_ROOT_DIR%/}/${TRSYS_OUT_REL}"
        log_info "build_target contains trsys, trsys_dir=${TRSYS_DIR}"
    else
        TRSYS_WORKDIR="${ROOT_DIR}"
        TRSYS_DIR="${ROOT_DIR%/}/${TRSYS_OUT_REL}"
        log_info "NEW_TRSYSTEM_ROOT empty, trsys via pipe_main in ${TRSYS_WORKDIR}, trsys_dir=${TRSYS_DIR}"
    fi
elif [[ -n "${TRSYS_ROOT_DIR}" ]]; then
    if [[ ! -d "${TRSYS_ROOT_DIR}" ]]; then
        log_error "trsys root directory not found: ${TRSYS_ROOT_DIR}"
        exit 1
    fi
    TRSYS_DIR="${TRSYS_ROOT_DIR%/}/${TRSYS_OUT_REL}"
else
    TRSYS_DIR=""
fi

########################################
# prepare log
########################################
{
    echo "================ PREPARE INFO ================"
    echo "time            : $(date '+%F %T')"
    echo "root_dir        : ${ROOT_DIR}"
    echo "system_dir      : ${SYSTEM_DIR}"
    echo "vendor_dir      : ${VENDOR_DIR}"
    echo "project         : ${PROJECT}"
    echo "build_varient   : ${BUILD_VARIENT}"
    echo "build_flag      : ${BUILD_FLAG}"
    echo "build_targets   : ${TARGET_STR}"
    echo "sys_version     : ${SYS_VERSION}"
    echo "project_dir     : ${PROJECT_DIR}"
    echo "full_mk         : ${FULL_MK}"
    echo "vnd_mk          : ${VND_MK}"
    echo "odm_mk          : ${ODM_MK}"
    echo "PROJECT_SYS     : ${PROJECT_SYS}"
    echo "PROJECT_HAL     : ${PROJECT_HAL}"
    echo "PROJECT_KRN     : ${PROJECT_KRN}"
    echo "PROJECT_VEXT    : ${PROJECT_VEXT}"
    echo "PROJECT_ODM     : ${PROJECT_ODM}"
    echo "trsys_root_dir  : ${TRSYS_ROOT_DIR}"
    echo "trsys_workdir   : ${TRSYS_WORKDIR}"
    echo "trsys_dir       : ${TRSYS_DIR}"
    echo "has_trsys_target: ${HAS_TRSYS_TARGET}"
    echo "status_dir      : ${STATUS_DIR}"
    echo "================================================"
} > "${PREPARE_LOG}"

log_info "prepare info saved to ${PREPARE_LOG}"

########################################
# status / pid / timing helpers
########################################
status_file() {
    local target="$1"
    echo "${STATUS_DIR}/${target}.status"
}

pid_file() {
    local target="$1"
    echo "${STATUS_DIR}/${target}.pid"
}

time_file() {
    local target="$1"
    echo "${STATUS_DIR}/${target}.time"
}

write_status() {
    local target="$1"
    local status="$2"
    local code="${3:-0}"
    local file
    file="$(status_file "${target}")"
    {
        echo "target=${target}"
        echo "status=${status}"
        echo "exit_code=${code}"
        echo "time=$(date '+%F %T')"
    } > "${file}"
}

write_time_info() {
    local target="$1"
    local start_epoch="$2"
    local end_epoch="$3"
    local duration="$4"
    local file
    file="$(time_file "${target}")"
    {
        echo "target=${target}"
        echo "start_epoch=${start_epoch}"
        echo "end_epoch=${end_epoch}"
        echo "duration_sec=${duration}"
    } > "${file}"
}

########################################
# cleanup on Ctrl+C / SIGTERM
########################################
cleanup_children() {
    log_error "received interrupt signal, cleaning running child processes..."

    local t pf pid
    for t in "${BUILD_LIST[@]:-}"; do
        pf="$(pid_file "${t}")"
        if [[ -f "${pf}" ]]; then
            pid="$(cat "${pf}")"
            if kill -0 "${pid}" 2>/dev/null; then
                log_error "killing target=${t}, pid=${pid}"
                kill "${pid}" 2>/dev/null || true
            fi
        fi
    done

    sleep 2

    for t in "${BUILD_LIST[@]:-}"; do
        pf="$(pid_file "${t}")"
        if [[ -f "${pf}" ]]; then
            pid="$(cat "${pf}")"
            if kill -0 "${pid}" 2>/dev/null; then
                log_error "force killing target=${t}, pid=${pid}"
                kill -9 "${pid}" 2>/dev/null || true
            fi
        fi
    done

    log_error "cleanup done"
    exit 130
}

trap cleanup_children INT TERM

########################################
# run build target
########################################
run_build_target() {
    local target="$1"
    local logfile="${ROOT_DIR}/build_${target}_${TIMESTAMP}.log"

    (
        local start_epoch end_epoch duration rc
        start_epoch="$(now_epoch)"

        write_status "${target}" "RUNNING" 0

        local workdir=""
        local lunch=""
        local cmd=""

        case "${target}" in
            sys)
                workdir="${SYSTEM_DIR}"
                lunch="${PROJECT_SYS}"
                cmd="bash tran_build --component sys --lunch ${lunch} --apk-use false --release ${BUILD_FLAG} --variant ${BUILD_VARIENT}"
                if [[ -n "${SYS_VERSION}" ]]; then
                    cmd="${cmd} --version ${SYS_VERSION}"
                fi
                ;;
            krn)
                workdir="${VENDOR_DIR}"
                lunch="${PROJECT_KRN}"
                cmd="bash tran_build --component krn --lunch ${lunch} --apk-use false --release ${BUILD_FLAG} --variant ${BUILD_VARIENT}"
                ;;
            vext)
                workdir="${VENDOR_DIR}"
                lunch="${PROJECT_VEXT}"
                cmd="bash tran_build --component vext --lunch ${lunch} --apk-use false --release ${BUILD_FLAG} --variant ${BUILD_VARIENT}"
                ;;
            hal)
                workdir="${VENDOR_DIR}"
                lunch="${PROJECT_HAL}"
                cmd="bash tran_build --component hal --lunch ${lunch} --apk-use false --release ${BUILD_FLAG} --variant ${BUILD_VARIENT}"
                ;;
            odm)
                workdir="${VENDOR_DIR}"
                lunch="${PROJECT_ODM}"
                cmd="bash tran_build --component odm --lunch ${lunch} --apk-use false --release ${BUILD_FLAG} --variant ${BUILD_VARIENT}"
                ;;
            trsys)
                workdir="${TRSYS_WORKDIR:-${ROOT_DIR}}"
                lunch="trsys"
                cmd="trsys-pipeline"
                ;;
            *)
                echo "[ERROR] unsupported target: ${target}" >> "${logfile}"
                end_epoch="$(now_epoch)"
                duration=$((end_epoch - start_epoch))
                write_time_info "${target}" "${start_epoch}" "${end_epoch}" "${duration}"
                write_status "${target}" "FAILED" 1
                exit 1
                ;;
        esac

        {
            echo "=================================================="
            echo "target      : ${target}"
            echo "project     : ${PROJECT}"
            echo "variant     : ${BUILD_VARIENT}"
            echo "flag        : ${BUILD_FLAG}"
            echo "workdir     : ${workdir}"
            echo "lunch       : ${lunch}"
            echo "cmd         : ${cmd}"
            echo "start_time  : $(date '+%F %T')"
            echo "start_epoch : ${start_epoch}"
            echo "log_file    : ${logfile}"
            echo "=================================================="
        } > "${logfile}"

        cd "${workdir}" || {
            echo "[ERROR] failed to cd to ${workdir}" >> "${logfile}"
            end_epoch="$(now_epoch)"
            duration=$((end_epoch - start_epoch))
            write_time_info "${target}" "${start_epoch}" "${end_epoch}" "${duration}"
            write_status "${target}" "FAILED" 2
            exit 2
        }

        if [[ "${target}" == "trsys" ]]; then
            local conf_file="${workdir}/conf.json"
            local pipe_trsys_dir="${workdir}/.pipe/trsys"
            rc=0

            if [[ ! -f "${conf_file}" ]]; then
                echo "[ERROR] conf.json not found: ${conf_file}" >> "${logfile}"
                rc=1
            else
                if [[ -d "${pipe_trsys_dir}" ]]; then
                    echo "[INFO] ${pipe_trsys_dir} exists, skip setup" >> "${logfile}"
                else
                    echo "[INFO] cmd: pipe_main --mode comp -c trsys -s setup -f conf.json" >> "${logfile}"
                    invoke_pipe_main --mode comp -c trsys -s setup -f conf.json >> "${logfile}" 2>&1
                    rc=$?
                fi

                if [[ ${rc} -eq 0 ]]; then
                    echo "[INFO] cmd: pipe_main --mode comp -c trsys -s repo" >> "${logfile}"
                    invoke_pipe_main --mode comp -c trsys -s repo >> "${logfile}" 2>&1
                    rc=$?
                fi

                if [[ ${rc} -eq 0 ]]; then
                    echo "[INFO] cmd: pipe_main --mode comp -c trsys -s build --local" >> "${logfile}"
                    invoke_pipe_main --mode comp -c trsys -s build --local >> "${logfile}" 2>&1
                    rc=$?
                fi
            fi
        else
            bash -lc "${cmd}" >> "${logfile}" 2>&1
            rc=$?
        fi
        end_epoch="$(now_epoch)"
        duration=$((end_epoch - start_epoch))
        write_time_info "${target}" "${start_epoch}" "${end_epoch}" "${duration}"

        if [[ ${rc} -eq 0 ]]; then
            echo "[INFO] target ${target} build success" >> "${logfile}"
            echo "[INFO] duration: $(format_duration "${duration}")" >> "${logfile}"
            write_status "${target}" "SUCCESS" 0
            exit 0
        else
            echo "[ERROR] target ${target} build failed, rc=${rc}" >> "${logfile}"
            echo "[ERROR] duration: $(format_duration "${duration}")" >> "${logfile}"
            write_status "${target}" "FAILED" "${rc}"
            exit "${rc}"
        fi
    ) &

    local bgpid=$!
    echo "${bgpid}" > "$(pid_file "${target}")"
    log_info "started target=${target}, pid=${bgpid}, log=${logfile}"
}

########################################
# launch build
########################################
NEED_PACK=0
declare -a BUILD_LIST=()

for t in "${TARGETS[@]}"; do
    if [[ "${t}" == "pack" ]]; then
        NEED_PACK=1
    else
        BUILD_LIST+=("${t}")
    fi
done

if [[ ${#BUILD_LIST[@]} -eq 0 ]]; then
    log_info "no compile targets specified, only pack requested"
fi

for t in "${BUILD_LIST[@]}"; do
    run_build_target "${t}"
done

########################################
# monitor all child process
########################################
declare -A FINISHED=()
declare -A RESULT=()
declare -A EXITCODE=()
declare -A DURATION_SEC=()

TOTAL=${#BUILD_LIST[@]}
DONE=0

while [[ ${DONE} -lt ${TOTAL} ]]; do
    sleep "${KEEPALIVE_INTERVAL}"

    for t in "${BUILD_LIST[@]}"; do
        if [[ -n "${FINISHED[$t]+x}" ]]; then
            continue
        fi

        pf="$(pid_file "${t}")"
        if [[ ! -f "${pf}" ]]; then
            log_error "pid file missing for target ${t}"
            continue
        fi

        pid="$(cat "${pf}")"
        if kill -0 "${pid}" 2>/dev/null; then
            echo -e "${COLOR_GREEN}[${t}][PID:${pid}] 进行中... $(date '+%T')${COLOR_RESET}"
        else
            sf="$(status_file "${t}")"
            tf="$(time_file "${t}")"

            if [[ -f "${sf}" ]]; then
                st="$(grep '^status=' "${sf}" | tail -n1 | cut -d= -f2-)"
                ec="$(grep '^exit_code=' "${sf}" | tail -n1 | cut -d= -f2-)"
            else
                st="FAILED"
                ec="999"
            fi

            if [[ -f "${tf}" ]]; then
                du="$(grep '^duration_sec=' "${tf}" | tail -n1 | cut -d= -f2-)"
            else
                du="0"
            fi

            FINISHED["$t"]=1
            RESULT["$t"]="${st}"
            EXITCODE["$t"]="${ec}"
            DURATION_SEC["$t"]="${du}"
            DONE=$((DONE + 1))

            if [[ "${st}" == "SUCCESS" ]]; then
                log_info "target ${t} finished: status=${st}, exit_code=${ec}, duration=$(format_duration "${du}")"
            else
                log_error "target ${t} finished: status=${st}, exit_code=${ec}, duration=$(format_duration "${du}")"
            fi
        fi
    done
done

########################################
# summary
########################################
log_info "all compile tasks finished, summary below:"
ALL_SUCCESS=1

for t in "${BUILD_LIST[@]}"; do
    st="${RESULT[$t]:-UNKNOWN}"
    ec="${EXITCODE[$t]:-999}"
    du="${DURATION_SEC[$t]:-0}"
    fd="$(format_duration "${du}")"

    if [[ "${st}" == "SUCCESS" ]]; then
        echo -e "${COLOR_GREEN}  - ${t}: ${st} (exit_code=${ec}, duration=${fd})${COLOR_RESET}"
    else
        echo -e "${COLOR_RED}  - ${t}: ${st} (exit_code=${ec}, duration=${fd})${COLOR_RESET}"
        ALL_SUCCESS=0
    fi
done

########################################
# pack
########################################
if [[ ${NEED_PACK} -eq 1 ]]; then
    if [[ ${ALL_SUCCESS} -ne 1 ]]; then
        log_error "pack requested, but not all compile targets succeeded, skip pack"
        exit 1
    fi

    log_info "all compile targets succeeded, start pack"

    systemdir="${SYSTEM_DIR}/out_sys/target/product/${PROJECT_SYS}/images"
    vendordir="${VENDOR_DIR}/out_hal/target/product/${PROJECT_HAL}/images"
    kerneldir="${VENDOR_DIR}/out_krn/target/product/${PROJECT_KRN}/images"
    vextdir="${VENDOR_DIR}/out_vext/target/product/${PROJECT_VEXT}/images"
    odmdir="${VENDOR_DIR}/out_odm/target/product/${PROJECT}/images"

    if [[ -z "${systemdir}" ]]; then log_error "pack failed: systemdir not found"; exit 1; fi
    if [[ -z "${vendordir}" ]]; then log_error "pack failed: vendordir not found"; exit 1; fi
    if [[ -z "${kerneldir}" ]]; then log_error "pack failed: kerneldir not found"; exit 1; fi
    if [[ -z "${vextdir}" ]]; then log_error "pack failed: vextdir not found"; exit 1; fi
    if [[ -z "${odmdir}" ]]; then log_error "pack failed: odmdir not found"; exit 1; fi

    PACK_LOG="${ROOT_DIR}/build_pack_${TIMESTAMP}.log"

    PACK_OUTPUT_DIR="${ROOT_DIR}/output_version_${PROJECT}"

    {
        echo "=================================================="
        echo "pack start : $(date '+%F %T')"
        echo "systemdir  : ${systemdir}"
        echo "vendordir  : ${vendordir}"
        echo "kerneldir  : ${kerneldir}"
        echo "vextdir    : ${vextdir}"
        echo "odmdir     : ${odmdir}"
        echo "trsys_dir  : ${TRSYS_DIR}"
        echo "output_dir : ${PACK_OUTPUT_DIR}"
        echo "=================================================="
    } > "${PACK_LOG}"

    # 切换到 SYSTEM_DIR，如果失败则记录错误并退出
    cd "${SYSTEM_DIR}" || {
        log_error "pack failed: failed to cd to ${SYSTEM_DIR}"
        exit 1
    }

    # 执行打包脚本（output_dir 使用切换目录前的路径）
    declare -a PACK_CMD=(
        python vendor/mediatek/proprietary/scripts/releasetools/split_build.py
        --system-dir "${systemdir}"
        --vendor-dir "${vendordir}"
        --kernel-dir "${kerneldir}"
        --vext-dir "${vextdir}"
        --odm-dir "${odmdir}"
        --output-dir "${PACK_OUTPUT_DIR}"
    )

    if [[ -n "${TRSYS_DIR}" && -d "${TRSYS_DIR}" ]]; then
        PACK_CMD+=(--trsystem-dir "${TRSYS_DIR}")
        log_info "trsys dir exists, pack append --trsystem-dir ${TRSYS_DIR}"
        echo "pack extra  : --trsystem-dir ${TRSYS_DIR}" >> "${PACK_LOG}"
    else
        if [[ ${HAS_TRSYS_TARGET} -eq 1 ]]; then
            log_error "pack failed: trsys was built but dir not found: ${TRSYS_DIR}"
            echo "[ERROR] trsys dir missing: ${TRSYS_DIR}" >> "${PACK_LOG}"
            exit 1
        fi
        log_info "trsys dir not found, pack without --trsystem-dir"
        echo "pack extra  : (no --trsystem-dir)" >> "${PACK_LOG}"
    fi

    "${PACK_CMD[@]}" >> "${PACK_LOG}" 2>&1

    PACK_RC=$?
    if [[ ${PACK_RC} -eq 0 ]]; then
        log_info "pack success, log: ${PACK_LOG}"
        exit 0
    else
        log_error "pack failed, rc=${PACK_RC}, log: ${PACK_LOG}"
        exit "${PACK_RC}"
    fi
else
    if [[ ${ALL_SUCCESS} -eq 1 ]]; then
        log_info "all requested compile targets succeeded, no pack requested"
        exit 0
    else
        log_error "some compile targets failed"
        exit 1
    fi
fi
