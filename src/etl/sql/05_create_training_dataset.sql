CREATE TABLE IF NOT EXISTS ecommerce.training_dataset
(
    timestamp Int64,
    visitorid UInt64,
    itemid UInt64,
    event_time DateTime64(3, 'UTC'),

    target UInt8,

    views UInt64,
    purchases UInt64,
    ctr Float64,

    categoryid Nullable(UInt32),
    available Nullable(UInt8),

    hour UInt8,
    weekday UInt8
)
ENGINE = MergeTree()
ORDER BY (event_time, itemid, visitorid);