(defproject ooni-pipeline "0.0.1-SNAPSHOT"
  :source-paths ["src/clj" "topologies"]
  :resource-paths ["_resources"]
  :target-path "_build"
  :min-lein-version "2.0.0"
  :jvm-opts ["-client"]
  :repositories {"HDP Releases" "http://repo.hortonworks.com/content/repositories/releases"}
  :dependencies  [
                  [org.apache.storm/storm-core "0.9.3.2.2.4.2-2"]
                  [org.apache.storm/storm-kafka "0.9.3.2.2.4.2-2"]
                  [org.apache.kafka/kafka_2.10 "0.8.1.2.2.4.2-2" :exclusions [com.sun.jmx/jmxri com.sun.jdmk/jmxtools javax.jms/jms org.slf4j/slf4j-api]]
                  [org.apache.zookeeper/zookeeper "3.4.6.2.2.4.2-2" :exclusions [io.netty/netty org.slf4j/slf4j-api org.slf4j/slf4j-log4j12]]
                  [com.parsely/streamparse "0.0.4-SNAPSHOT"]
                  ]
  :jar-exclusions     [#"log4j\.properties" #"backtype" #"trident" #"META-INF" #"meta-inf" #"\.yaml"]
  :uberjar-exclusions [#"log4j\.properties" #"backtype" #"trident" #"META-INF" #"meta-inf" #"\.yaml"]
  )
