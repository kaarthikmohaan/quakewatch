# Target-analyst interview guide

**Status:** Prepared on 1 October 2026; no analyst has been interviewed. This
guide implements the target-user check in [the design](design.md). Do not mark
it complete from the project owner's Cortex scan comparison.

## Finding one participant

The owner has no existing target-analyst contact. A practical referral route is
the [International Association of Emergency Managers' Asia council](https://www.iaem.org/global/iaem-asia/),
whose public page includes India and invites contact with its leadership. Ask
for a referral to a practitioner who compares historical hazard records for
facilities or preparedness work. This is a recruitment lead, not a confirmed
participant, and no membership or purchase is needed to review the public
page. The project team has not contacted the council or any individual.

Suggested short invitation for the owner to send if they choose:

> I am building a small educational batch warehouse that compares historical
> USGS earthquake records near three public example cities. Would a facilities
> planning or preparedness analyst be willing to spend about 15 minutes trying
> one comparison task and telling me what is useful or misleading? This is
> research feedback, not an alert or safety tool. I will share the known data
> gaps up front and can keep their notes anonymous.

## Participant and task

Ask one facilities-planning or community-preparedness analyst who actually
compares historical earthquake records. Use only the public Seattle, San
Francisco, and Anchorage example sites. Ask them to compare recorded event
counts and magnitude distributions over the five-year project horizon, then
explain whether revision history and missing-window notes affect their
interpretation. The task is retrospective analysis, not a safety decision.

Before the session, prepare the same dates, site radius, magnitude threshold,
and question for both methods. Check that the QuakeWatch result covers the
chosen intervals; history windows 12, 42, and 73 are missing, so show those
gaps explicitly. The catalog-wide update sweep is incomplete. Do not present
the warehouse as a complete or current USGS catalog. Any new Snowflake query
requires the owner's compute-cost approval first. Do not restart USGS source
retries for this interview.

## Session script

1. Ask: “How do you usually answer a five-year, cross-site earthquake-history
   question?” Record the tools and steps they normally use.
2. Give the fixed comparison question. Start a timer while they use their
   usual method; stop when they have an answer or say they cannot complete it.
   Record elapsed time and what they could verify.
3. Show the equivalent QuakeWatch result and its coverage/revision notes.
   Start a new timer while they find an answer; record elapsed time and any
   confusion or caveats they notice. Do not coach them toward a positive answer.
4. Ask: “Would this comparison be useful in your work? What is missing or
   misleading? Would you trust it enough to use for retrospective planning?”
5. Show the optional Cortex brief only after the SQL result. Ask whether the
   brief helps them find the same facts; record any wrong or overstated claim.

## Record after the session

| Field | Notes |
|---|---|
| Date, participant role, and anonymized ID | Pending |
| Fixed sites, dates, radius, magnitude threshold | Pending |
| Manual method and elapsed time | Pending |
| QuakeWatch result and elapsed time | Pending |
| Predeclared improvement target, set before timing | Pending |
| Answer correctness and coverage-gap understanding | Pending |
| Usefulness verdict and reasons | Pending |
| Cortex brief verdict and factual errors, if shown | Pending |
| Query IDs or saved evidence, if a live query was approved | Pending |

Report observed times and the participant's own words without generalizing
from one person. A missing answer, unresolved coverage, or inaccurate brief is
an outcome to record, not a reason to discard the session.
