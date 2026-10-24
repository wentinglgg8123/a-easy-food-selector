-- Add half-star ratings to an existing food picker reviews installation.
-- Safe to rerun. No existing rows, IDs, timestamps, or text are changed.
-- Old reviews remain unrated (NULL); there is deliberately no rating default.
-- Run this in the Supabase SQL editor before deploying the rating-aware app.
begin;

alter table public.restaurant_reviews add column if not exists rating numeric;

do $$
begin
    if not exists (
        select 1 from pg_catalog.pg_constraint
        where conname = 'restaurant_reviews_rating_half_star_check'
          and conrelid = 'public.restaurant_reviews'::regclass
    ) then
        alter table public.restaurant_reviews
            add constraint restaurant_reviews_rating_half_star_check
            check (rating is null or (rating between 1 and 5 and mod(rating, 0.5) = 0));
    end if;
end;
$$;

alter table public.restaurant_reviews enable row level security;
revoke all on table public.restaurant_reviews from public, anon, authenticated;
-- Existing column grants stay intact; the server gains only the new input column.
grant insert (rating) on public.restaurant_reviews to service_role;

-- Do not replace the old RPC: its original return type remains compatible.
create or replace function public.food_picker_reviews_for_restaurants_v2(
    restaurant_ids text[], review_limit integer default 3
)
returns table (
    id uuid, restaurant_id text, author text, body text, created_at timestamptz, rating numeric
)
language plpgsql
stable
security invoker
set search_path = public, pg_temp
as $$
begin
    if restaurant_ids is null or cardinality(restaurant_ids) = 0 then
        return;
    end if;
    if cardinality(restaurant_ids) > 24 then
        raise exception 'At most 24 restaurant IDs are allowed';
    end if;
    if review_limit is null or review_limit not between 1 and 10 then
        raise exception 'Review limit must be between 1 and 10';
    end if;
    if exists (
        select 1 from unnest(restaurant_ids) as requested(value)
        where requested.value is null
           or requested.value !~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$'
    ) then
        raise exception 'Invalid restaurant ID';
    end if;
    return query
        select ranked.id, ranked.restaurant_id, ranked.author, ranked.body, ranked.created_at, ranked.rating
        from (
            select reviews.id, reviews.restaurant_id, reviews.author, reviews.body, reviews.created_at, reviews.rating,
                row_number() over (
                    partition by reviews.restaurant_id
                    order by reviews.created_at desc, reviews.id desc
                ) as review_position
            from public.restaurant_reviews as reviews
            where reviews.restaurant_id = any (restaurant_ids)
        ) as ranked
        where ranked.review_position <= review_limit
        order by ranked.restaurant_id, ranked.created_at desc, ranked.id desc;
end;
$$;

revoke all on function public.food_picker_reviews_for_restaurants_v2(text[], integer)
    from public, anon, authenticated;
grant execute on function public.food_picker_reviews_for_restaurants_v2(text[], integer)
    to service_role;

notify pgrst, 'reload schema';

commit;
