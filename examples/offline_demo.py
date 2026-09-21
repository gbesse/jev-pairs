# Purpose: Demonstrate cascade and fixture pair judgment offline.
from jev_pairs import dedupe,FakeJev
rule={"id":"product","version":"1","statement":"Same product","true":{},"false":{},"key_fields":["name"]}
items=[{"id":"a","name":"Red shoe"},{"id":"b","name":"red shoes"},{"id":"c","name":"Blue hat"}]
fake=FakeJev({"a|b":.91});result=dedupe(items,rule,fake,certain_below=.1,certain_above=.99)
print({"source":"synthetic fixture, not measured Jev output","groups":result["groups"],"provider_calls":len(fake.calls),"cost":result["cost"]})
