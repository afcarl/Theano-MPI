import glob
import time
import os

import numpy as np

import hickle as hkl


def unpack_configs(config, ext_data='.hkl', ext_label='.npy'):
    flag_para_load = config['para_load']
    flag_top_5 = config['flag_top_5']
    # Load Training/Validation Filenames and Labels
    train_folder = config['dir_head'] + config['train_folder']
    val_folder = config['dir_head'] + config['val_folder']
    label_folder = config['dir_head'] + config['label_folder']
    train_filenames = sorted(glob.glob(train_folder + '/*' + ext_data))
    val_filenames = sorted(glob.glob(val_folder + '/*' + ext_data))
    train_labels = np.load(label_folder + 'train_labels' + ext_label)
    val_labels = np.load(label_folder + 'val_labels' + ext_label)
    img_mean = np.load(config['dir_head'] + config['mean_file'])
    img_mean = img_mean[:, :, :, np.newaxis].astype('float32')
    
    return (flag_para_load, flag_top_5,
            train_filenames, val_filenames, train_labels, val_labels, img_mean)

def get_bad_list(n_batches, commsize):
   
    bad_left = n_batches % commsize
    bad_left_list =[]
    for bad in range(bad_left):
        bad_left_list.append(n_batches-(bad+1)) 
    return bad_left_list
    
def extend_data(config,filenames, labels, env):

    size = config['size']
    rank = config['rank']
    file_batch_size = config['file_batch_size']
    
    lmdb_cur_list=None    
    
    if config['data_source']=='hkl':
    
        n_files = len(filenames)
        labels = labels[:n_files*file_batch_size]  # cut unused labels 
           
        # get a list of training filenames that cannot be allocated to any rank
        bad_left_list = get_bad_list(n_files, size)
        if rank == 0: print 'bad list is '+str(bad_left_list)
        need = (size - len(bad_left_list))  % size  
        if need !=0: 
            filenames.extend(filenames[-1*need:])
            labels=labels.tolist()
            labels.extend(labels[-1*need*file_batch_size:])
        n_files = len(filenames)
            
    elif config['data_source']=='lmdb':
        img_num = env.stat()['entries']
        n_files = img_num//file_batch_size # cut unused labels 
        labels = labels[:n_files*file_batch_size]
        
        bad_left_list = get_bad_list(n_files, size)
        if rank == 0: print 'bad list is ' + str(bad_left_list)
        need = (size - len(bad_left_list))  % size  
        
        lmdb_cur_list = [index*file_batch_size for index in range(n_files)]
        
        if need !=0: 
            lmdb_cur_list.extend(lmdb_cur_list[-1*need:])
            labels=labels.tolist()
            labels.extend(labels[-1*need*file_batch_size:])
            n_files = len(lmdb_cur_list)
            
    elif config['data_source']=='both':
    
        n_files = len(filenames)
        labels = labels[:n_files*file_batch_size] # cut unused labels 
         
        print 'total hkl files' , n_files          
        # get a list of training filenames that cannot be allocated to any rank
        bad_left_list = get_bad_list(n_files, size)
        if rank == 0: print 'bad list is '+str(bad_left_list)
        need = (size - len(bad_left_list))  % size  
        
        lmdb_cur_list = [index*file_batch_size for index in range(n_files)]
        
        if need !=0:
            lmdb_cur_list.extend(lmdb_cur_list[-1*need:])
            filenames.extend(filenames[-1*need:])
            labels=labels.tolist()
            labels.extend(labels[-1*need*file_batch_size:])
            n_files = len(filenames)
    
    return filenames, labels, lmdb_cur_list, n_files


# for CUDA-aware MPI
bufint_cn= lambda arr: arr.container.value.as_buffer(arr.container.value.size*4,0)
bufint = lambda arr: arr.gpudata.as_buffer(arr.nbytes)

def dtype_to_mpi(t):
    from mpi4py import MPI
    if hasattr(MPI, '_typedict'):
        mpi_type = MPI._typedict[np.dtype(t).char]
    elif hasattr(MPI, '__TypeDict__'):
        mpi_type = MPI.__TypeDict__[np.dtype(t).char]
    else:
        raise ValueError('cannot convert type')
    return mpi_type

def get_rand3d(config, mode):  
    
    if mode == 'val':
        return np.float32([0.5, 0.5, 0])
        
    else:
        
        if config['random'] and config['rand_crop'] == True:
        
            time_seed = int(time.time())*int(config['worker_id'])%1000

            np.random.seed(time_seed)
            tmp_rand = np.float32(np.random.rand(3))
            tmp_rand[2] = round(tmp_rand[2])
            return tmp_rand
        else:
            return np.float32([0.5, 0.5, 0]) 
        
def save_weights(layers, weights_dir, epoch):
    for idx in range(len(layers)):
        if hasattr(layers[idx], 'W'):
            layers[idx].W.save_weight(
                weights_dir, 'W' + '_' + str(idx) + '_' + str(epoch))
        if hasattr(layers[idx], 'W0'):
            layers[idx].W0.save_weight(
                weights_dir, 'W0' + '_' + str(idx) + '_' + str(epoch))
        if hasattr(layers[idx], 'W1'):
            layers[idx].W1.save_weight(
                weights_dir, 'W1' + '_' + str(idx) + '_' + str(epoch))
        if hasattr(layers[idx], 'b'):
            layers[idx].b.save_weight(
                weights_dir, 'b' + '_' + str(idx) + '_' + str(epoch))
        if hasattr(layers[idx], 'b0'):
            layers[idx].b0.save_weight(
                weights_dir, 'b0' + '_' + str(idx) + '_' + str(epoch))
        if hasattr(layers[idx], 'b1'):
            layers[idx].b1.save_weight(
                weights_dir, 'b1' + '_' + str(idx) + '_' + str(epoch))



def load_weights(layers, weights_dir, epoch, l_range=None):
    
    for idx in range(len(layers)):
        
        if l_range !=None and (idx not in l_range):
            continue
            
        if hasattr(layers[idx], 'W'):
            layers[idx].W.load_weight(
                weights_dir, 'W' + '_' + str(idx) + '_' + str(epoch))
        if hasattr(layers[idx], 'W0'):
            layers[idx].W0.load_weight(
                weights_dir, 'W0' + '_' + str(idx) + '_' + str(epoch))
        if hasattr(layers[idx], 'W1'):
            layers[idx].W1.load_weight(
                weights_dir, 'W1' + '_' + str(idx) + '_' + str(epoch))
        if hasattr(layers[idx], 'b'):
            layers[idx].b.load_weight(
                weights_dir, 'b' + '_' + str(idx) + '_' + str(epoch))
        if hasattr(layers[idx], 'b0'):
            layers[idx].b0.load_weight(
                weights_dir, 'b0' + '_' + str(idx) + '_' + str(epoch))
        if hasattr(layers[idx], 'b1'):
            layers[idx].b1.load_weight(
                weights_dir, 'b1' + '_' + str(idx) + '_' + str(epoch))


def save_momentums(vels, weights_dir, epoch):
    for ind in range(len(vels)):
        np.save(os.path.join(weights_dir, 'mom_' + str(ind) + '_' + str(epoch)),
                vels[ind].get_value())


def load_momentums(vels, weights_dir, epoch):
    for ind in range(len(vels)):
        vels[ind].set_value(np.load(os.path.join(
            weights_dir, 'mom_' + str(ind) + '_' + str(epoch) + '.npy')))
