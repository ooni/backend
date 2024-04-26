-- Create tables for integration tests

CREATE TABLE default.incidents 
(
    `id` String,
    `title` String,
    `short_description` String,
    `text` String,
    `start_time` Datetime DEFAULT now(),
    `end_time` Nullable(Datetime),
    `create_time` Datetime,
    `update_time` Datetime DEFAULT now(),
    `creator_account_id` FixedString(32),
    `reported_by` String,
    `email_address` String,
    `event_type` LowCardinality(String),
    `published` UInt8,
    `deleted` UInt8 DEFAULT 0,
    `CCs` Array(FixedString(2)),
    `ASNs` Array(String),
    `domains` Array(String),
    `tags` Array(String),
    `links` Array(String),
    `test_names` Array(String), 
)
ENGINE=ReplacingMergeTree
ORDER BY (create_time, creator_account_id, id)
SETTINGS index_granularity = 8192;