import duckdb

con = duckdb.connect()
con.execute("SET memory_limit = '3GB'")
con.execute("SET threads = 2")

print("=== СОБЫТИЯ ===")
print(
    con.execute("""
        SELECT event, COUNT(*) AS count
        FROM read_csv_auto('events.csv')
        GROUP BY event
        ORDER BY count DESC
    """).df().to_string(index=False)
)

print("\n=== СВОЙСТВА ТОВАРОВ ===")
for path in [
    "item_properties_part1.csv",
    "item_properties_part2.csv",
]:
    print(f"\n{path}")
    print(
        con.execute(f"""
            SELECT property, COUNT(*) AS count
            FROM read_csv_auto('{path}')
            WHERE property IN ('categoryid', 'available')
            GROUP BY property
            ORDER BY property
        """).df().to_string(index=False)
    )

con.close()
