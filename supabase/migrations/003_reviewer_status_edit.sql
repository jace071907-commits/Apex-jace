-- =====================================================================
-- APEX · Disputes and Intakes — reviewers can now change STATUS from Edit Review.
-- Run once in Supabase Dashboard -> SQL Editor, AFTER 002_admin_reviews.sql.
-- Only replaces the APEX trigger function; no table or data changes.
--
-- Change vs 002: the reviewer's "Associate updated a pend" notification is sent only when the change
-- was made by someone other than the reviewer (UPDATED_BY <> REVIEWER_DOMAIN), so reviewers are not
-- notified about their own status edits. The associate still gets "Pend status changed".
-- =====================================================================
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

  -- Status / note changes ----------------------------------------------------
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

  if v_reviewer is not null
     and new."UPDATED_BY" is distinct from v_reviewer
     and (new."STATUS" is distinct from old."STATUS"
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
