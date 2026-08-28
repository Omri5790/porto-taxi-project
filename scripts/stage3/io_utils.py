"""Filesystem helpers that behave the same locally and on Dataproc.

Stage 3 used to write its results with a bare ``open("output/...")``.  On a
Dataproc cluster that path is the *driver node's own disk*, which the deployment
script deletes together with the cluster a few lines later -- so the cloud run
produced nothing that outlived it.  Everything here goes through the Hadoop
FileSystem API when the path is a ``gs://`` (or ``hdfs://``) URI, so results
land in the bucket and survive the teardown.
"""

from __future__ import annotations

import json
import os


def is_remote(path: str) -> bool:
    return path.startswith("gs://") or path.startswith("hdfs://") or path.startswith("s3a://")


def write_text(spark, path: str, text: str) -> None:
    if not is_remote(path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return

    sc = spark.sparkContext
    jvm = sc._jvm
    hconf = sc._jsc.hadoopConfiguration()
    uri = jvm.java.net.URI(path)
    fs = jvm.org.apache.hadoop.fs.FileSystem.get(uri, hconf)
    out = fs.create(jvm.org.apache.hadoop.fs.Path(path), True)
    try:
        out.write(bytearray(text.encode("utf-8")))
    finally:
        out.close()


def write_json(spark, path: str, payload) -> None:
    write_text(spark, path, json.dumps(payload, indent=2, ensure_ascii=False))


def join(base: str, name: str) -> str:
    return f"{base.rstrip('/')}/{name}"
