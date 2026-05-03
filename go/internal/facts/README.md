# Facts

`facts` defines the durable records PCG writes before graph projection. These
types are the contract between collection, parsing, queueing, projection, and
reducer-owned materialization.

Avoid convenience fields that only help one caller. A fact should describe source
truth clearly enough for retries, repair, and replay.
