-- =====================================================================
-- APEX · Disputes and Intakes — Admin (reviewer) module
-- Run once in Supabase Dashboard -> SQL Editor, AFTER 001_disputes_and_intakes.sql.
-- Idempotent: only ADDs columns / replaces APEX functions. Never drops or rewrites data.
-- =====================================================================

-- 1. New Pend columns ---------------------------------------------------
alter table public."Pend"
  add column if not exists "REVIEWER_DOMAIN" text,
  add column if not exists "SUB_STATUS"      text;

create index if not exists pend_review_queue_idx on public."Pend" ("STATUS", "REVIEWER_DOMAIN", "DATE_PENDED");
create index if not exists pend_reviewer_idx     on public."Pend" ("REVIEWER_DOMAIN", "DATE_REVIEWED" desc);

-- 2. Notification kinds for reviewers ----------------------------------
alter table public.apex_notification drop constraint if exists apex_notification_kind_check;
alter table public.apex_notification add constraint apex_notification_kind_check
  check (kind in ('review', 'status', 'valid', 'invalid', 'ack', 'pend_update', 'review_update'));

-- 3. BEFORE trigger: keep a reviewer-entered DATE_REVIEWED (only default it when empty) --
create or replace function public.apex_pend_before() returns trigger
language plpgsql set search_path = public as $$
begin
  if new."DATE_PENDED" is null then
    new."DATE_PENDED" := public.apex_today();
  end if;
  new."PENDED_DAYS" := greatest(public.apex_today() - new."DATE_PENDED"::date, 0);
  new."REVIEWER_DOMAIN" := nullif(trim(coalesce(new."REVIEWER_DOMAIN", '')), '');

  if tg_op = 'UPDATE' then
    if (to_jsonb(new) - 'PENDED_DAYS' - 'UPDATED_AT') is distinct from (to_jsonb(old) - 'PENDED_DAYS' - 'UPDATED_AT') then
      new."UPDATED_AT" := now();
    end if;
    if new."PEND_REVIEW" is distinct from old."PEND_REVIEW"
       or new."REVIEWER_REMARKS" is distinct from old."REVIEWER_REMARKS" then
      new."ACKNOWLEDGED" := false;
      new."ACKNOWLEDGED_BY" := null;
      new."ACKNOWLEDGED_AT" := null;
      if new."PEND_REVIEW" is not null and new."DATE_REVIEWED" is null then
        new."DATE_REVIEWED" := public.apex_today();
      end if;
    end if;
  end if;
  return new;
end $$;

-- 4. AFTER trigger: history + notifications for associates AND reviewers --
create or replace function public.apex_pend_after() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_id       text := new."id"::text;
  v_inq      text := coalesce(new."INQUIRY_NUMBER", '—');
  v_kind     text;
  v_reviewer text := nullif(trim(coalesce(new."REVIEWER_DOMAIN", '')), '');
  v_who      text := coalesce(new."ASSIGNED_TO", new."DOMAIN", 'The associate');
begin
  if tg_op = 'INSERT' then
    insert into apex_pend_history (pend_id, inquiry_number, domain, action, status, note, changed_by)
    values (v_id, new."INQUIRY_NUMBER", new."DOMAIN", 'Created', new."STATUS", new."REMARKS",
            coalesce(new."UPDATED_BY", new."DOMAIN"));
    return new;
  end if;

  -- Associate-side changes -------------------------------------------------
  if new."STATUS" is distinct from old."STATUS" then
    insert into apex_pend_history (pend_id, inquiry_number, domain, action, status, note, changed_by, details)
    values (v_id, new."INQUIRY_NUMBER", new."DOMAIN", 'Status Changed', new."STATUS", new."LAST_NOTE",
            new."UPDATED_BY", jsonb_build_object('from', old."STATUS", 'to', new."STATUS"));
    insert into apex_notification (domain, pend_id, inquiry_number, kind, title, message)
    values (new."DOMAIN", v_id, new."INQUIRY_NUMBER", 'status', 'Pend status changed',
            format('Inquiry %s changed from %s to %s.', v_inq, coalesce(old."STATUS", '—'), coalesce(new."STATUS", '—')));
  elsif new."LAST_NOTE" is distinct from old."LAST_NOTE" or new."SUB_STATUS" is distinct from old."SUB_STATUS" then
    insert into apex_pend_history (pend_id, inquiry_number, domain, action, status, note, changed_by, details)
    values (v_id, new."INQUIRY_NUMBER", new."DOMAIN", 'Pend Updated', new."STATUS", new."LAST_NOTE", new."UPDATED_BY",
            jsonb_build_object('sub_status', new."SUB_STATUS"));
  end if;

  if v_reviewer is not null and (new."STATUS" is distinct from old."STATUS"
       or new."LAST_NOTE" is distinct from old."LAST_NOTE" or new."SUB_STATUS" is distinct from old."SUB_STATUS") then
    insert into apex_notification (domain, pend_id, inquiry_number, kind, title, message)
    values (v_reviewer, v_id, new."INQUIRY_NUMBER", 'pend_update', 'Associate updated a pend',
            format('%s updated inquiry %s (status: %s).', v_who, v_inq, coalesce(new."STATUS", '—')));
  end if;

  -- Review changes -----------------------------------------------------------
  if new."PEND_REVIEW" is distinct from old."PEND_REVIEW"
     or new."REVIEWER_REMARKS" is distinct from old."REVIEWER_REMARKS"
     or new."REVIEWER" is distinct from old."REVIEWER" then
    v_kind := case new."PEND_REVIEW" when 'Valid' then 'valid' when 'Invalid' then 'invalid' else 'review' end;
    insert into apex_pend_history (pend_id, inquiry_number, domain, action, status, note, changed_by, details)
    values (v_id, new."INQUIRY_NUMBER", new."DOMAIN",
            case when old."PEND_REVIEW" is null then 'Reviewed' else 'Review Updated' end,
            new."STATUS", new."REVIEWER_REMARKS", coalesce(new."REVIEWER", v_reviewer),
            jsonb_build_object('review', new."PEND_REVIEW", 'previous', old."PEND_REVIEW"));
    insert into apex_notification (domain, pend_id, inquiry_number, kind, title, message)
    values (new."DOMAIN", v_id, new."INQUIRY_NUMBER", v_kind,
            case v_kind when 'valid' then 'Pend marked Valid' when 'invalid' then 'Pend marked Invalid'
                        else 'Reviewer submitted a review' end,
            format('%s reviewed inquiry %s%s', coalesce(new."REVIEWER", 'A reviewer'), v_inq,
                   case when v_kind = 'invalid' then ' — acknowledgement required.' else '.' end));
    -- Reviewer is told when an existing review's result changes (not on the first review they just submitted).
    if v_reviewer is not null and old."PEND_REVIEW" is not null and new."PEND_REVIEW" is distinct from old."PEND_REVIEW" then
      insert into apex_notification (domain, pend_id, inquiry_number, kind, title, message)
      values (v_reviewer, v_id, new."INQUIRY_NUMBER", 'review_update', 'Review status changed',
              format('Inquiry %s review changed from %s to %s.', v_inq, old."PEND_REVIEW", coalesce(new."PEND_REVIEW", '—')));
    end if;
  end if;

  -- Acknowledgement ----------------------------------------------------------
  if new."ACKNOWLEDGED" and not coalesce(old."ACKNOWLEDGED", false) then
    insert into apex_pend_history (pend_id, inquiry_number, domain, action, status, note, changed_by)
    values (v_id, new."INQUIRY_NUMBER", new."DOMAIN", 'Review Acknowledged', new."STATUS", null, new."ACKNOWLEDGED_BY");
    if v_reviewer is not null then
      insert into apex_notification (domain, pend_id, inquiry_number, kind, title, message)
      values (v_reviewer, v_id, new."INQUIRY_NUMBER", 'ack', 'Associate acknowledged review',
              format('%s acknowledged your %s review on inquiry %s.', v_who, coalesce(new."PEND_REVIEW", ''), v_inq));
    end if;
  end if;
  return new;
end $$;
