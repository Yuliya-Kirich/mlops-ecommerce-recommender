INSERT INTO ecommerce.item_categories_history
    (itemid, property_time, categoryid)
SELECT
    itemid,
    property_time,
    toUInt32OrNull(value) AS categoryid
FROM ecommerce.item_properties_raw
WHERE property = 'categoryid';
