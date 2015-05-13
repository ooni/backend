(defproject ooni-pipeline "0.0.1-SNAPSHOT"
  :source-paths ["topologies"]
  :resource-paths ["_resources"]
  :target-path "_build"
  :min-lein-version "2.0.0"
  :jvm-opts ["-client"]
  :repositories {"HDP Releases" "http://repo.hortonworks.com/content/repositories/releases"}
  :dependencies  [[org.apache.storm/storm-core "0.9.3.2.2.4.2-2"]
                  [com.parsely/streamparse "0.0.4-SNAPSHOT"]
                  ]
  :jar-exclusions     [#"log4j\.properties" #"backtype" #"trident" #"META-INF" #"meta-inf" #"\.yaml"]
  :uberjar-exclusions [#"log4j\.properties" #"backtype" #"trident" #"META-INF" #"meta-inf" #"\.yaml"]
  )
