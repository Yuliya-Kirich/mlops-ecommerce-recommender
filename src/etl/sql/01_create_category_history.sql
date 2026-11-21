CREATE TABLE IF NOT EXISTS ecommerce.item_categories_history
(
    itemid UInt64,
    property_time DateTime64(3, 'UTC'),
    categoryid Nullable(UInt32)
)
ENGINE = MergeTree()
ORDER BY (itemid, property_time);
