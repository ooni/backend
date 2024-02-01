import csv

TABLE_CREATE_QUERIES = """
CREATE TABLE fastpath (
  measurement_uid TEXT,
  report_id TEXT,
  input TEXT,
  probe_cc TEXT,
  probe_asn INTEGER,
  test_name TEXT,
  test_start_time TEXT,
  measurement_start_time TEXT,
  filename TEXT,
  scores TEXT,
  platform TEXT,
  anomaly TEXT,
  confirmed TEXT,
  msm_failure TEXT,
  domain TEXT,
  software_name TEXT,
  software_version TEXT,
  control_failure TEXT,
  blocking_general REAL,
  is_ssl_expected INTEGER,
  page_len INTEGER,
  page_len_ratio REAL,
  server_cc TEXT,
  server_asn INTEGER,
  server_as_name TEXT,
  update_time TEXT,
  test_version TEXT,
  architecture TEXT,
  engine_name TEXT,
  engine_version TEXT,
  test_runtime REAL,
  blocking_type TEXT,
  test_helper_address TEXT,
  test_helper_type TEXT,
  ooni_run_link_id TEXT
);

CREATE TABLE citizenlab (
    domain TEXT, 
    url TEXT,
    cc TEXT,
    category_code TEXT
);
"""

# Dumps for fastpath.csv and citizenlab.csv can be generated running the following commands on the backend-fsn host:
"""
clickhouse-client -q "SELECT * FROM fastpath WHERE measurement_start_time > '2024-01-01' AND measurement_start_time < '2024-01-10' ORDER BY measurement_start_time LIMIT 1000 INTO OUTFILE '20240110-fastpath.csv' FORMAT CSVWithNames"
clickhouse-client -q "SELECT * FROM citizenlab INTO OUTFILE '20240110-citizenlab.csv' FORMAT CSVWithNames"
"""
FASTPATH_CSV = "fastpath.csv"
CITIZENLAB_CSV = "citizenlab.csv"

OUTPUT_SQL = "db-fixtures.sql"

with open(OUTPUT_SQL, "w") as f:
    f.write(TABLE_CREATE_QUERIES)

    input_set = set()
    # Process fastpath.csv
    with open(FASTPATH_CSV) as fastpath_csv:
        reader = csv.DictReader(fastpath_csv)
        for row in reader:
            input_set.add(row["input"])
            columns = ",".join(row.keys())
            values = ",".join([f"'{v.strip()}'" for v in row.values()])
            query = f"INSERT INTO fastpath ({columns}) VALUES ({values});\n"
            f.write(query)

    # Process citizenlab.csv
    with open(CITIZENLAB_CSV) as citizenlab_csv:
        reader = csv.DictReader(citizenlab_csv)
        for row in reader:
            if row["url"] not in input_set:
                continue
            row["cc"] = row["cc"][:2]
            columns = ",".join(row.keys())
            values = ",".join([f"'{v.strip()}'" for v in row.values()])
            query = f"INSERT INTO citizenlab ({columns}) VALUES ({values});\n"
            f.write(query)

print("SQL file generated successfully!")
