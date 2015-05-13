(ns report
  (:use     [streamparse.specs])
  (:gen-class))

(defn report [options]
   [
    ;; spout configuration
    {"report-spout" (python-spout-spec
          options
          "spouts.reports.S3ReportsSpout"
          ["report-id", "record-type", "report-json"]
          :p 24
          )
    }
    ;; bolt configuration
    {"kafka-bolt" (python-bolt-spec
          options
          {"report-spout" ["report-id"]}
          "bolts.reports.KafkaBolt"
          []
          :p 12
          )
    }
  ]
)
