# PROPOSED only. No build/pull until root reviews the admission packet.
FROM --platform=linux/amd64 docker.io/library/python@sha256:9ce5a4e59b833c002e1c4196c60ec0b38977e3235d626298ba7ffe2e64f5a30c AS curated
ENV PYTHONDONTWRITEBYTECODE=1
COPY curate.py base-file-sha256.json linux_bootstrap.py /opt/qm-build/
COPY licenses/ /opt/qm-build/licenses/
RUN --network=none ["/usr/local/bin/python3", "-B", "-I", "/opt/qm-build/curate.py"]

FROM scratch
COPY --from=curated /qm-rootfs/ /
ENV PATH=/usr/local/bin LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
WORKDIR /output
ENTRYPOINT ["/usr/local/bin/python3", "-B", "-I", "/opt/quantmesh/linux_bootstrap.py"]
