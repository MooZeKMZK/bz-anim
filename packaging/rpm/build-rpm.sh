#!/usr/bin/env bash
# Build modular RPM (.rpm) and RPK (.rpk) packages for bz-anim:
#   - python3-bz-anim-core
#   - bz-anim-cli
#   - bz-anim-tui
#   - bz-anim-gui
#   - bz-anim
set -euo pipefail

VERSION="${1:-0.1.0}"
VERSION="${VERSION#v}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${2:-${ROOT_DIR}/dist/rpm}"
RPM_TOPDIR="$(mktemp -d)"
trap 'rm -rf "${RPM_TOPDIR}"' EXIT

mkdir -p "${OUT_DIR}" "${RPM_TOPDIR}"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# Create source tarball matching Source0: bz-anim-%{version}.tar.gz
STAGE_DIR="$(mktemp -d)"
mkdir -p "${STAGE_DIR}/bz-anim-${VERSION}"
cp -a "${ROOT_DIR}/pyproject.toml" "${ROOT_DIR}/config.toml" "${ROOT_DIR}/theme.toml" \
      "${ROOT_DIR}/src" "${ROOT_DIR}/packages" "${ROOT_DIR}/packaging" \
      "${STAGE_DIR}/bz-anim-${VERSION}/"
tar -C "${STAGE_DIR}" -czf "${RPM_TOPDIR}/SOURCES/bz-anim-${VERSION}.tar.gz" "bz-anim-${VERSION}"
rm -rf "${STAGE_DIR}"

cp "${ROOT_DIR}/packaging/rpm/bz-anim.spec" "${RPM_TOPDIR}/SPECS/bz-anim.spec"

rpmbuild -bb \
  --define "_topdir ${RPM_TOPDIR}" \
  --define "_version ${VERSION}" \
  "${RPM_TOPDIR}/SPECS/bz-anim.spec"

find "${RPM_TOPDIR}/RPMS" -name "*.rpm" -exec cp -v {} "${OUT_DIR}/" \;

# Also produce .rpk bundle archive alongside .rpm packages so both .rpm and .rpk consumers are supported
for rpm_file in "${OUT_DIR}"/*.rpm; do
  base_name="$(basename "${rpm_file}" .rpm)"
  cp "${rpm_file}" "${OUT_DIR}/${base_name}.rpk"
done

echo "Built RPM/RPK packages in ${OUT_DIR}:"
ls -lh "${OUT_DIR}"
