(ns report
  (:use     
      [backtype.storm.clojure]
      [report.spouts.report_uri_spout :only [spout] :rename {spout report-uri-spout}]
      [streamparse.specs]
  )
  (:gen-class))

(defn report [options]
   [
    ;; spout configurations
    {"report-uri-spout" (spout-spec report-uri-spout :p 1)}

    ;; bolt configuration
    {
      
      "report-parse-bolt" (python-bolt-spec
        options
        {"report-uri-spout" :shuffle}
        "bolts.reports.ReportParseBolt"
        ["report-id", "record-type", "report-json"]
        :p 24)

      "kafka-bolt" (python-bolt-spec
        options
        {"report-parse-bolt" ["report-id"]}
        "bolts.reports.KafkaBolt"
        []
        :p 12)


    }
  ]
)
