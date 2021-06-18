WITH byteam AS (
    SELECT
        count(*) OVER (PARTITION BY team),
        row_number(*) OVER (PARTITION BY team ORDER BY random()),
        name,
        team
    FROM users
    ORDER BY 1, 2
)
SELECT
    ((row_number() OVER ()-1)%$1)+1,
    name,
    team
FROM byteam
ORDER BY 1