#include "header.cuh"
#include "gpu_memory.cuh"
#include "gpu_macros.cuh"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <sys/time.h>

 int read_initial_conditions(const char* filename, int NUM, int block_size, double** y_host, double** y_device, double** variable_host, double** variable_device, mechanism_memory** h_mem, mechanism_memory** d_mem, int device=0) {
    //bytes per thread
    size_t mech_size = get_required_size();
    cudaDeviceProp props;
    cudaErrorCheck( cudaGetDeviceProperties(&props, device) );
    //memory size in bytes
    size_t mem_avail = props.totalGlobalMem;
    //conservatively estimate the maximum allowable threads
    int max_threads = int(floor(0.8 * float(mech_size) / float(mem_avail)));
    int padded = max_threads * block_size;

    initialize_gpu_memory(padded, h_mem, d_mem, y_device, variable_device);
    (*y_host) = (double*)malloc(NUM * NN * sizeof(double));
    (*variable_host) = (double*)malloc(NUM * sizeof(double));
    FILE *fp = fopen (filename, "rb");
    if (fp == NULL)
    {
        fprintf(stderr, "Could not open file: %s\\n", filename);
        exit(1);
    }
    double buffer[NN + 2];

    // load temperature and mass fractions for all threads (cells)
    for (int i = 0; i < NUM; ++i)
    {
        // read line from data file
        int count = fread(buffer, sizeof(double), NN + 2, fp);
        if (count != (NN + 2))
        {
            fprintf(stderr, "File (%s) is incorrectly formatted, %d doubles were expected but only %d were read.\\n", filename, NN + 1, count);
            exit(-1);
        }
        //apply mask if necessary
        apply_mask(&buffer[3]);
        //put into y_host
        (*y_host)[i] = buffer[1];
#ifdef CONP
        (*variable_host)[i] = buffer[2];
#elif CONV
        double pres = buffer[2];
#endif
        for (int j = 0; j < NSP; j++)
            (*y_host)[i + (j + 1) * NUM] = buffer[j + 3];

        // if constant volume, calculate density
#ifdef CONV
        double Yi[NSP];
        double Xi[NSP];

        for (int j = 1; j < NN; ++j)
        {
            Yi[j - 1] = (*y_host)[i + j * NUM];
        }

        mass2mole (Yi, Xi);
        (*variable_host)[i] = getDensity ((*y_host)[i], pres, Xi);
#endif
    }
    fclose (fp);
    return padded;
}