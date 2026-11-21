INSERT INTO ecommerce.training_dataset
(
    timestamp, visitorid, itemid, event_time,
    target, views, purchases, ctr,
    categoryid, available, hour, weekday
)
SELECT
    v.timestamp,
    v.visitorid,
    v.itemid,
    v.event_time,
    v.target,
    v.views,
    v.purchases,
    v.ctr,
    c.categoryid,
    a.available,
    toHour(v.event_time) AS hour,
    toDayOfWeek(v.event_time, 1) AS weekday
FROM
(
    SELECT *
    FROM ecommerce.views_with_history
    ORDER BY itemid, event_time
) AS v
ASOF LEFT JOIN
(
    SELECT itemid, property_time, categoryid
    FROM ecommerce.item_categories_history
    ORDER BY itemid, property_time
) AS c
ON v.itemid = c.itemid
AND v.event_time >= c.property_time
ASOF LEFT JOIN
(
    SELECT itemid, property_time, available
    FROM ecommerce.item_availability_history
    ORDER BY itemid, property_time
) AS a
ON v.itemid = a.itemid
AND v.event_time >= a.property_time
SETTINGS
    join_use_nulls = 1,
    max_threads = 2;
