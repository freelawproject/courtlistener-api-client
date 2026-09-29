from prometheus_client import multiprocess


def child_exit(server, worker):
    # Run prometheus cleanup on child exit
    multiprocess.mark_process_dead(worker.pid)
