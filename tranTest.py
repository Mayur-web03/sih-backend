from etherTransaction.supa import TransactionTracer

START_ADDRESS = "0x846943093f519A47734765BEF9EE1136800bEb9C"

tracer = TransactionTracer(
    start_address=START_ADDRESS,
    max_hops=5,
    offset=100,
    start_block=0,
    end_block=999999999,
    chain_id="11155111"
)

print("Tracer created!")

inward_df, outward_df = tracer.run_both()

print("\n========== INWARD ==========")
print(inward_df)

print("\n========== OUTWARD ==========")
print(outward_df)