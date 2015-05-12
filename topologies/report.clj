(ns report
  (:use     [streamparse.specs])
  (:gen-class))

(defn report [options]
   [
    ;; spout configuration
    {"report-spout" (python-spout-spec
          options
          "spouts.reports.S3ReportsSpout"
          ["report-id", "report-json"])
    }
    ;; bolt configuration
    {"kafka-bolt" (python-bolt-spec
          options
          {"report-spout" ["report-id"]}
          "bolts.reports.KafkaBolt"
          [])
    }
  ]
)
