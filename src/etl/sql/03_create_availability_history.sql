CREATE TABLE IF NOT EXISTS ecommerce.item_availability_history
(
    itemid UInt64,
    property_time DateTime64(3, 'UTC'),
    available Nullable(UInt8)
)
ENGINE = MergeTree()
ORDER BY (itemid, property_time);
