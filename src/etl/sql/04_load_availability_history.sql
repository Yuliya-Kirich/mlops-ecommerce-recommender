INSERT INTO ecommerce.item_availability_history
    (itemid, property_time, available)
SELECT
    itemid,
    property_time,
    toUInt8OrNull(value) AS available
FROM ecommerce.item_properties_raw
WHERE property = 'available';
