#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* A deliberately buggy program to demonstrate gdb core-dump triage.
   compute_stats() dereferences a NULL pointer -> SIGSEGV -> core dump. */

typedef struct {
    int   count;
    double *samples;   /* left NULL on purpose */
} Dataset;

static double compute_stats(Dataset *ds) {
    double sum = 0.0;
    for (int i = 0; i < ds->count; i++) {
        sum += ds->samples[i];   /* <-- NULL deref when samples == NULL */
    }
    return sum / ds->count;
}

static double process(Dataset *ds) {
    printf("processing %d samples...\n", ds->count);
    return compute_stats(ds);
}

int main(int argc, char **argv) {
    Dataset ds;
    ds.count   = 5;
    ds.samples = NULL;    /* the bug: never allocated */

    double avg = process(&ds);
    printf("average = %f\n", avg);
    return 0;
}
